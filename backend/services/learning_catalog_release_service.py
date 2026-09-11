from __future__ import annotations

from content.formal_curriculum_registry import formal_content_validation_identity, formal_registered_boundary
from services.learning_curriculum_preparation_contract import (canonical_preparation_target_for, formal_target_course_count, preparation_authority_grade)

from dataclasses import dataclass
import hashlib
import logging
import re
import unicodedata
import uuid
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Sequence

from content.primary_skill_boundaries import (
    CONTENT_VALIDATION_CONTRACT_VERSION,
    PRIMARY_CURRICULUM_VERSION,
    PRIMARY_ONE_CONTENT_DATASET_SHA256,
    PRIMARY_SKILL_BOUNDARIES,
    SUBJECT_LANGUAGE_POLICY_VERSION,
)
from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from repositories.learning_catalog_repository import (
    LearningCatalogActivationError,
    LearningCatalogBuildConflict,
    LearningCatalogRepository,
)
from repositories.learning_question_fingerprint_inventory import (
    provider_question_fingerprint_projection,
)
from services.learning_catalog_validator import LearningCatalogValidator
from services.learning_curriculum_preparation_contract import (
    build_preparation_target,
    preparation_target_fingerprint,
)
from services.learning_generation_failure_policy import (
    is_transient_generation_failure,
)
from services.learning_provider_deadline_contract import (
    provider_attempt_deadline_is_valid,
)
from services.learning_content_recovery import recovery_dispatches
from integrations.openmaic_question_adapter import (
    QUESTION_CONTRACT_VERSION,
    QUESTION_PHASE_EXECUTION_AUTHORITY,
    QUESTION_PHASE_IO,
    QUESTION_PHASE_TRANSITIONS,
    QuestionPhaseCommand,
    normalize_question_phase_provider_profile,
    question_phase_execution_authority,
)
from services.dynamic_learning_course_generation_service import ContentPhaseWork
from services.learning_catalog_validator import (
    PrimaryOneCourseTarget,
    PrimaryOneValidatedVariant,
)
from services.learning_generated_course_validator import (
    AcceptedPrimaryOneHostReceipt,
    PrimaryOneHostGateControlError,
    PrimaryOneHostGateDependencyError,
    PrimaryOneHostGateIdentity,
    QuestionPhaseCourseEvidence,
    QuestionPhaseProviderProfileEvidence,
)


SUPPORTED_GRADES = frozenset(f"primary_{grade}" for grade in range(1, 7))
SUPPORTED_SUBJECTS = frozenset({"chinese", "math", "english"})
_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_RESTRICTED_CREATE_KEYS = frozenset(
    {
        "executionMode",
        "stageCeiling",
        "contentManifestVersion",
        "canaryManifest",
        "preparationTarget",
        "preparation_target",
        "targetFingerprint",
    }
)
_QUESTION_CONTENT_VALIDATION_FAILURE_CODES = frozenset(
    {
        "question_phase_output_rejected",
        "question_phase_json_rejected",
        "question_phase_verification_json_rejected",
        "question_phase_verification_answers_rejected",
        "question_phase_verification_numeric_rejected",
        "question_phase_verification_review_rejected",
        "question_phase_verification_semantic_rejected",
        "question_phase_verification_checkpoint_rejected",
    }
)


@dataclass(frozen=True)
class ContentAdvanceResult:
    kind: Literal[
        "progressed",
        "busy",
        "dependency_retry",
        "failed",
        "handoff",
        "stale",
    ]
    build_id: str
    item_id: str | None
    content_summary: Mapping[str, object]


@dataclass(frozen=True)
class ContentWorkUnitClaim:
    build_id: str
    item_id: str
    item_lease_token: str
    logical_attempt: int
    content_phase: str
    work_unit_kind: Literal["provider_phase", "host_gate"]
    work_unit_deadline_at: int


@dataclass(frozen=True)
class ContentDispatchGraphAuditSnapshot:
    item_id: str
    logical_attempt: int
    dispatch_ids: tuple[str, ...]
    final_phase: str
    final_phase_ordinal: int


@dataclass(frozen=True)
class ContentParentRetryAuditSnapshot:
    build_id: str
    release_id: str
    authority_class: Literal[
        "pre_provider_dependency", "host_only_dependency", "not_replayable"
    ]
    provider_dispatch_ids: tuple[str, ...]
    open_or_ambiguous_dispatch_ids: tuple[str, ...]
    failed_safe_dispatch_ids: tuple[str, ...]
    provider_graph_complete: bool
    next_work_kind: Literal["host_gate"] | None
    build_error_code: str | None


@dataclass(frozen=True)
class ContentProviderDependencyAuditSnapshot:
    build_id: str
    release_id: str
    item_id: str
    logical_attempt: int
    content_phase: str
    predecessor_dispatch_ids: tuple[str, ...]
    predecessor_final_phase: str | None
    predecessor_final_phase_ordinal: int | None


@dataclass(frozen=True)
class ContentHostDependencyAuditSnapshot:
    build_id: str
    release_id: str
    item_id: str
    logical_attempt: int
    content_phase: Literal["host_gate_running"]
    dispatch_ids: tuple[str, ...]


@dataclass(frozen=True)
class ContentProofAuditSnapshot:
    build_id: str
    release_id: str
    passed_item_ids: tuple[str, ...]
    repairable_item_ids: tuple[str, ...]
    terminal_failed_item_ids: tuple[str, ...]


class LearningCatalogReleaseService:
    """Build and atomically activate a student-visible primary catalog."""

    def __init__(
        self,
        database_url: str | Path,
        *,
        dynamic_generation_service: Any,
        lesson_package_service: Any,
        catalog_validator: LearningCatalogValidator | None = None,
        staged_content_candidate_generator: Any | None = None,
        primary_one_host_validator: Any | None = None,
        question_phase_provider_profiles: Mapping[str, object] | None = None,
        clock_ms: Callable[[], int] = now_ms,
        repository: LearningCatalogRepository | None = None,
    ):
        self.repository = repository or LearningCatalogRepository(Database(database_url))
        self.dynamic_generation_service = dynamic_generation_service
        self.lesson_package_service = lesson_package_service
        self.catalog_validator = catalog_validator or LearningCatalogValidator()
        self.staged_content_candidate_generator = staged_content_candidate_generator
        self.primary_one_host_validator = primary_one_host_validator
        self.question_phase_provider_profiles = (
            dict(question_phase_provider_profiles)
            if isinstance(question_phase_provider_profiles, Mapping)
            else None
        )
        self._content_clock_ms = clock_ms

    def advance_grade_validation(
        self,
        *,
        grade_code: str,
        build_id: str,
        release_id: str,
        target_fingerprint: str,
        publisher_plan_id: str,
        publisher_lease_token: str,
        preparation_repository: Any,
        provider_readiness_client: Any,
        route_probe_service: Any,
        route_probe_client: Any,
    ) -> dict[str, int]:
        """Advance final 30-item validation and preparation handoff."""

        return self._advance_grade_validation(
            grade_code=grade_code,
            build_id=build_id,
            release_id=release_id,
            target_fingerprint=target_fingerprint,
            publisher_plan_id=publisher_plan_id,
            publisher_lease_token=publisher_lease_token,
            preparation_repository=preparation_repository,
            provider_readiness_client=provider_readiness_client,
            route_probe_service=route_probe_service,
            route_probe_client=route_probe_client,
            publisher_stage="validating",
            allow_partial=False,
        )

    def advance_progressive_grade_validation(
        self,
        *,
        grade_code: str,
        build_id: str,
        release_id: str,
        target_fingerprint: str,
        publisher_plan_id: str,
        publisher_lease_token: str,
        publisher_stage: str,
        preparation_repository: Any,
        provider_readiness_client: Any,
        route_probe_service: Any,
        route_probe_client: Any,
    ) -> dict[str, int]:
        """Advance the release witness for currently audio-ready items."""

        if publisher_stage not in {
            "generating_content",
            "building_classrooms",
            "generating_speech",
            "validating",
        }:
            raise LearningCatalogActivationError(
                "progressive validation stage is invalid"
            )
        return self._advance_grade_validation(
            grade_code=grade_code,
            build_id=build_id,
            release_id=release_id,
            target_fingerprint=target_fingerprint,
            publisher_plan_id=publisher_plan_id,
            publisher_lease_token=publisher_lease_token,
            preparation_repository=preparation_repository,
            provider_readiness_client=provider_readiness_client,
            route_probe_service=route_probe_service,
            route_probe_client=route_probe_client,
            publisher_stage=publisher_stage,
            allow_partial=True,
        )

    def _advance_grade_validation(
        self,
        *,
        grade_code: str,
        build_id: str,
        release_id: str,
        target_fingerprint: str,
        publisher_plan_id: str,
        publisher_lease_token: str,
        preparation_repository: Any,
        provider_readiness_client: Any,
        route_probe_service: Any,
        route_probe_client: Any,
        publisher_stage: str,
        allow_partial: bool,
    ) -> dict[str, int]:
        """Advance one exact 059 job; an existing job is GET-only."""

        grade_code = self._identifier(grade_code, "gradeCode")
        build_id = self._identifier(build_id, "buildId")
        release_id = self._identifier(release_id, "releaseId")
        publisher_plan_id = self._identifier(publisher_plan_id, "publisherPlanId")
        publisher_lease_token = self._identifier(
            publisher_lease_token, "publisherLeaseToken"
        )
        if grade_code not in SUPPORTED_GRADES or re.fullmatch(
            r"[0-9a-f]{64}", str(target_fingerprint or "")
        ) is None:
            raise LearningCatalogActivationError(
                "formal grade validation identity is invalid"
            )
        with self.repository.transaction() as conn:
            prepare_args = {
                "grade_code": grade_code,
                "build_id": build_id,
                "release_id": release_id,
                "target_fingerprint": target_fingerprint,
                "publisher_plan_id": publisher_plan_id,
                "publisher_lease_token": publisher_lease_token,
                "now": int(self._content_clock_ms()),
            }
            if allow_partial:
                prepare_args.update({
                    "expected_stage": publisher_stage,
                    "allow_partial": True,
                })
            work = self.repository.prepare_formal_validation_step(
                conn,
                **prepare_args,
            )
        action = str(work.get("action") or "")
        if action == "route_probe":
            self._materialize_formal_route_probe(
                work,
                route_probe_service=route_probe_service,
                route_probe_client=route_probe_client,
            )
            with self.repository.transaction() as conn:
                prepare_args["now"] = int(self._content_clock_ms())
                work = self.repository.prepare_formal_validation_step(
                    conn,
                    **prepare_args,
                )
            action = str(work.get("action") or "")
        response = None
        if action == "start":
            evidence = work.get("evidence")
            if not isinstance(evidence, Mapping):
                raise LearningCatalogActivationError(
                    "formal Provider readiness evidence is incomplete"
                )
            response = provider_readiness_client.start_formal_provider_readiness(
                **dict(evidence)
            )
        elif action == "observe":
            response = provider_readiness_client.get_formal_provider_readiness(
                str(work.get("requestId") or "")
            )
        elif action not in {"complete", "idle"}:
            raise LearningCatalogActivationError(
                "formal Provider readiness work state is invalid"
            )
        with self.repository.transaction() as conn:
            if response is not None:
                persist_args = {
                    "grade_code": grade_code,
                    "build_id": build_id,
                    "release_id": release_id,
                    "target_fingerprint": target_fingerprint,
                    "publisher_plan_id": publisher_plan_id,
                    "publisher_lease_token": publisher_lease_token,
                    "response": response,
                    "now": int(self._content_clock_ms()),
                }
                if allow_partial:
                    persist_args.update({
                        "expected_stage": publisher_stage,
                        "allow_partial": True,
                    })
                self.repository.persist_formal_provider_readiness(
                    conn,
                    **persist_args,
                )
            counts = self.repository.formal_validation_counts(
                conn,
                grade_code=grade_code,
                build_id=build_id,
                release_id=release_id,
                target_fingerprint=target_fingerprint,
            )
            total = int(counts.get("total") or 0)
            ready = int(counts.get("ready") or 0)
            failed = int(counts.get("failed") or 0)
            ambiguous = int(counts.get("ambiguous") or 0)
            published = 0
            if (
                allow_partial
                and total > 0
                and ready == total
                and failed == 0
                and ambiguous == 0
            ):
                authority = (
                    self.repository.lock_progressive_formal_publication_authority(
                        conn,
                        grade_code=grade_code,
                        build_id=build_id,
                        release_id=release_id,
                        target_fingerprint=target_fingerprint,
                        publisher_plan_id=publisher_plan_id,
                        publisher_lease_token=publisher_lease_token,
                        publisher_stage=publisher_stage,
                        now=int(self._content_clock_ms()),
                    )
                )
                if int(authority.get("itemCount") or 0) > 0:
                    request_digest = hashlib.sha256(
                        (
                            f"{grade_code}|{build_id}|{target_fingerprint}"
                        ).encode("utf-8")
                    ).hexdigest()
                    publication_at = int(
                        authority.get("publishedAt")
                        or self._content_clock_ms()
                    )
                    self.repository.publish_formal_grade_release(
                        conn,
                        authority=authority,
                        publication_request_id=(
                            f"formal-progressive:{request_digest[:48]}"
                        ),
                        published_at=publication_at,
                        finalize_release=False,
                    )
                    published = (
                        preparation_repository.persist_progressive_formal_counts(
                            conn,
                            plan_id=publisher_plan_id,
                            lease_token=publisher_lease_token,
                            target_fingerprint=target_fingerprint,
                            expected_stage=publisher_stage,
                            now=publication_at,
                        )
                    )
            if (
                not allow_partial
                and total == formal_target_course_count(grade_code)
                and failed == 0
                and ambiguous == 0
            ):
                persisted, next_stage = (
                    preparation_repository.persist_formal_validation_progress(
                        conn,
                        plan_id=publisher_plan_id,
                        lease_token=publisher_lease_token,
                        target_fingerprint=target_fingerprint,
                        validation_ready_count=ready,
                        next_run_at=int(self._content_clock_ms()) + 1_000,
                        now=int(self._content_clock_ms()),
                    )
                )
                expected_stage = "publishing" if ready == formal_target_course_count(grade_code) else "validating"
                if not persisted or next_stage != expected_stage:
                    raise LearningCatalogActivationError(
                        "formal validation handoff authority is stale"
                    )
        result = {
            key: int(counts.get(key) or 0)
            for key in ("total", "ready", "failed", "ambiguous")
        }
        if allow_partial:
            result["published"] = int(published)
        return result

    def activate_grade_release(
        self,
        *,
        grade_code: str,
        build_id: str,
        target_fingerprint: str,
        publication_request_id: str,
        publisher_plan_id: str,
        publisher_lease_token: str,
        preparation_repository: Any,
        subject_progress: Mapping[str, object],
    ) -> dict[str, object]:
        """Publish and switch exactly one grade in one database transaction."""

        grade_code = self._identifier(grade_code, "gradeCode")
        build_id = self._identifier(build_id, "buildId")
        publisher_plan_id = self._identifier(publisher_plan_id, "publisherPlanId")
        publisher_lease_token = self._identifier(
            publisher_lease_token, "publisherLeaseToken"
        )
        if (
            grade_code not in SUPPORTED_GRADES
            or re.fullmatch(r"[0-9a-f]{64}", str(target_fingerprint or "")) is None
            or _REQUEST_ID.fullmatch(str(publication_request_id or "")) is None
            or not isinstance(subject_progress, Mapping)
        ):
            raise LearningCatalogActivationError(
                "formal publication identity is invalid"
            )
        activated_at = int(self._content_clock_ms())
        with self.repository.transaction() as conn:
            authority = self.repository.lock_formal_publication_authority(
                conn,
                grade_code=grade_code,
                build_id=build_id,
                target_fingerprint=target_fingerprint,
                publisher_plan_id=publisher_plan_id,
                publisher_lease_token=publisher_lease_token,
                publication_request_id=publication_request_id,
                now=activated_at,
            )
            if (
                int(authority.get("itemCount") or 0) != formal_target_course_count(grade_code)
                or int(authority.get("readyItemCount") or 0) != formal_target_course_count(grade_code)
                or re.fullmatch(
                    r"[0-9a-f]{64}",
                    str(authority.get("publicationReceiptSha256") or ""),
                )
                is None
            ):
                raise LearningCatalogActivationError(
                    "formal publication requires thirty exact ready items"
                )
            release_id = str(authority.get("releaseId") or "")
            publication_at = int(
                authority.get("publishedAt") or activated_at
            )
            self.repository.publish_formal_grade_release(
                conn,
                authority=authority,
                publication_request_id=publication_request_id,
                published_at=publication_at,
            )
            pointer = self.repository.activate_grade_release_pointer(
                conn,
                grade_code=grade_code,
                build_id=build_id,
                target_fingerprint=target_fingerprint,
                contract_version=LearningCatalogRepository.FORMAL_PUBLICATION_CONTRACT_VERSION,
                publication_request_id=publication_request_id,
                publication_receipt_hash=str(
                    authority["publicationReceiptSha256"]
                ),
                activated_at=publication_at,
            )
            completed = preparation_repository.complete_matching_formal_ready(
                conn,
                publisher_plan_id=publisher_plan_id,
                publisher_lease_token=publisher_lease_token,
                grade_code=grade_code,
                build_id=build_id,
                release_id=release_id,
                target_fingerprint=target_fingerprint,
                subject_progress=subject_progress,
                pointer=pointer,
                now=activated_at,
            )
            if int(completed) < 1:
                raise LearningCatalogActivationError(
                    "formal publication completed no current preparation plan"
                )
        return {
            "status": "ready",
            "stage": "completed",
            "gradeCode": grade_code,
            "releaseId": release_id,
            "completedPlanCount": int(completed),
        }

    @staticmethod
    def _materialize_formal_route_probe(
        work: Mapping[str, object], *, route_probe_service: Any, route_probe_client: Any
    ) -> None:
        runtime_id = str(work.get("runtimeClassroomId") or "")
        if not runtime_id or route_probe_service is None or route_probe_client is None:
            raise LearningCatalogActivationError(
                "formal route/session proof dependencies are unavailable"
            )
        probe = route_probe_service.issue_formal_candidate(runtime_id)
        receipts = route_probe_client.verify(probe)
        route_probe_service.finalize_probe(
            str(probe["probeId"]),
            chat_receipt=receipts["chat"],
            transcription_receipt=receipts["transcription"],
        )

    def advance_content(
        self,
        build_id: str,
        *,
        heartbeat: Callable[[], bool],
        bind_work_unit: Callable[[ContentWorkUnitClaim], bool] | None = None,
        authorize_control_work: Callable[[], bool] | None = None,
    ) -> ContentAdvanceResult:
        build_id = self._identifier(build_id, "buildId")
        if (
            self.staged_content_candidate_generator is None
            or self.primary_one_host_validator is None
            or set(self.question_phase_provider_profiles or {})
            != {"generator", "verifier"}
        ):
            return ContentAdvanceResult(
                kind="dependency_retry",
                build_id=build_id,
                item_id=None,
                content_summary=self._empty_content_summary(),
            )
        try:
            self._content_profile_payload("generator")
            self._content_profile_payload("verifier")
        except (KeyError, TypeError, ValueError):
            persisted_profile_failure = False
            if hasattr(self.repository, "inspect_content_profile_preflight"):
                with self.repository.transaction() as conn:
                    state = self.repository.inspect_content_profile_preflight(
                        conn, build_id=build_id
                    )
                    if state == "persisted":
                        self.repository.fence_content_failure(
                            conn,
                            build_id=build_id,
                            item_id=None,
                            error_code="preparation_content_contract_drift",
                            now=self._trusted_content_now(),
                        )
                        persisted_profile_failure = True
            if persisted_profile_failure:
                return ContentAdvanceResult(
                    kind="failed",
                    build_id=build_id,
                    item_id=None,
                    content_summary=self._content_summary_after_transition(
                        build_id,
                        terminal_already_fenced=True,
                    ),
                )
            return ContentAdvanceResult(
                kind="dependency_retry",
                build_id=build_id,
                item_id=None,
                content_summary=self._empty_content_summary(),
            )
        now = self._trusted_content_now()
        locked_handoff_validated = False
        locked_terminal_audit_failure = False
        with self.repository.transaction() as conn:
            plan: Mapping[str, object] = {}
            locked_audit = None
            if hasattr(self.repository, "load_content_proof_inventory"):
                inventory: Mapping[str, object] = {}
                try:
                    inventory = self.repository.load_content_proof_inventory(
                        conn, build_id=build_id
                    )
                    locked_audit = self._audit_locked_content_inventory(
                        conn=conn,
                        inventory=inventory,
                    )
                except (
                    PrimaryOneHostGateControlError,
                    PrimaryOneHostGateDependencyError,
                    KeyError,
                    TypeError,
                    ValueError,
                ):
                    self.repository.fence_content_failure(
                        conn,
                        build_id=build_id,
                        item_id=None,
                        error_code="preparation_content_contract_drift",
                        now=now,
                    )
                    plan = {
                        "action": "failed",
                        "items": inventory.get("items", ())
                        if isinstance(inventory, Mapping)
                        else (),
                    }
                    locked_terminal_audit_failure = True
            if not plan:
                if locked_audit is None:
                    plan = self.repository.prepare_content_advance(
                        conn, build_id=build_id, now=now
                    )
                else:
                    plan = self.repository.prepare_content_advance(
                        conn,
                        build_id=build_id,
                        now=now,
                        passed_item_ids=locked_audit["passedItemIds"],
                        repairable_item_ids=locked_audit[
                            "repairableItemIds"
                        ],
                        locked_attempt_histories_by_item=inventory.get(
                            "attemptHistoriesByItem", {}
                        ),
                    )
            if locked_audit is not None:
                plan = {
                    **dict(plan),
                    "contentSummary": locked_audit["summary"],
                }
                action = str(plan.get("action") or "stale")
                if action == "handoff":
                    self._validate_content_handoff_proofs(
                        locked_audit["proofs"]
                    )
                    locked_handoff_validated = True
                elif action == "attempt2":
                    raw_item = plan.get("item")
                    if isinstance(raw_item, Mapping):
                        locked_evidence = locked_audit["evidenceByItem"].get(
                            str(raw_item.get("id") or "")
                        )
                        if isinstance(locked_evidence, Mapping):
                            plan = {
                                **dict(plan),
                                "attemptOneEvidence": locked_evidence,
                            }
        if locked_terminal_audit_failure:
            return ContentAdvanceResult(
                kind="failed",
                build_id=build_id,
                item_id=None,
                content_summary=self._content_summary_after_transition(
                    build_id,
                    terminal_already_fenced=True,
                ),
            )
        items = plan.get("items")
        raw_summary = plan.get("contentSummary")
        summary = (
            raw_summary
            if isinstance(raw_summary, Mapping)
            else self._content_summary(items if isinstance(items, Sequence) else ())
        )
        action = str(plan.get("action") or "stale")
        item = plan.get("item")
        item_id = str(item.get("id")) if isinstance(item, Mapping) else None
        if action == "handoff":
            if not locked_handoff_validated:
                try:
                    self._validate_content_handoff(plan)
                except (PrimaryOneHostGateControlError, KeyError, TypeError, ValueError):
                    with self.repository.transaction() as conn:
                        self.repository.fence_content_failure(
                            conn,
                            build_id=build_id,
                            item_id=None,
                            error_code="preparation_content_contract_drift",
                            now=self._trusted_content_now(),
                        )
                    return ContentAdvanceResult(
                        "failed",
                        build_id,
                        None,
                        self._content_summary_after_transition(
                            build_id,
                            terminal_already_fenced=True,
                        ),
                    )
            return ContentAdvanceResult("handoff", build_id, None, summary)
        if action == "failed":
            return ContentAdvanceResult(
                kind="failed",
                build_id=build_id,
                item_id=item_id,
                content_summary=self._content_summary_after_transition(
                    build_id,
                    terminal_already_fenced=True,
                ),
            )
        if action in {"stale", "busy"}:
            return ContentAdvanceResult(
                kind={
                    "stale": "stale",
                    "busy": "busy",
                }[action],
                build_id=build_id,
                item_id=item_id,
                content_summary=summary,
            )
        if not isinstance(item, Mapping):
            return ContentAdvanceResult(
                kind="stale",
                build_id=build_id,
                item_id=None,
                content_summary=summary,
            )
        if action == "attempt2":
            return self._advance_content_attempt_two_after_authorization(
                build_id=build_id,
                expected_item_id=str(item["id"]),
                summary=summary,
                authorize_control_work=authorize_control_work,
            )
        if action == "provider":
            rejected = self._bind_content_work_unit_or_cleanup(
                build_id=build_id,
                action=action,
                item=item,
                summary=summary,
                bind_work_unit=bind_work_unit,
            )
            if rejected is not None:
                return rejected
            return self._advance_content_provider(
                build_id=build_id,
                plan=plan,
                item=item,
                summary=summary,
                heartbeat=heartbeat,
            )
        if action == "host":
            rejected = self._bind_content_work_unit_or_cleanup(
                build_id=build_id,
                action=action,
                item=item,
                summary=summary,
                bind_work_unit=bind_work_unit,
            )
            if rejected is not None:
                return rejected
            return self._advance_content_host(
                build_id=build_id,
                plan=plan,
                item=item,
                summary=summary,
            )
        return ContentAdvanceResult(
            kind="stale",
            build_id=build_id,
            item_id=item_id,
            content_summary=summary,
        )

    def audit_locked_content_proofs(
        self,
        conn,
        *,
        build_id: str,
    ) -> ContentProofAuditSnapshot:
        build_id = self._identifier(build_id, "buildId")
        inventory = self.repository.load_content_proof_inventory(
            conn, build_id=build_id
        )
        audit = self._audit_locked_content_inventory(
            conn=conn,
            inventory=inventory,
        )
        release = inventory.get("release")
        build = inventory.get("build")
        raw_items = inventory.get("items")
        if (
            not isinstance(release, Mapping)
            or not isinstance(build, Mapping)
            or not isinstance(raw_items, Sequence)
            or len(raw_items) != formal_target_course_count(build)
            or str(build.get("id") or "") != build_id
            or str(build.get("release_id") or "")
            != str(release.get("id") or "")
        ):
            raise ValueError("locked content proof projection identity drift")
        items = [item for item in raw_items if isinstance(item, Mapping)]
        if len(items) != formal_target_course_count(build):
            raise ValueError("locked content proof projection shape drift")
        item_order = tuple(str(item.get("id") or "") for item in items)
        if any(not item_id for item_id in item_order) or len(set(item_order)) != formal_target_course_count(build):
            raise ValueError("locked content proof projection item drift")
        item_ids = frozenset(item_order)

        def sealed_ids(key: str) -> frozenset[str]:
            raw = audit.get(key)
            if not isinstance(raw, (set, frozenset, tuple, list)):
                raise ValueError("locked content proof projection audit drift")
            values = frozenset(str(value) for value in raw)
            if not values.issubset(item_ids):
                raise ValueError("locked content proof projection escaped manifest")
            return values

        passed = sealed_ids("passedItemIds")
        repairable = sealed_ids("repairableItemIds")
        if passed & repairable:
            raise ValueError("locked content proof projection overlaps states")
        terminal_failed = frozenset(
            str(item["id"])
            for item in items
            if str(item.get("status") or "") == "failed"
            and str(item["id"]) not in repairable
        )
        if passed & terminal_failed or repairable & terminal_failed:
            raise ValueError("locked content proof projection overlaps failures")
        if len(passed) == formal_target_course_count(build):
            proofs = audit.get("proofs")
            if not isinstance(proofs, Sequence):
                raise ValueError("locked content handoff proofs are missing")
            self._validate_content_handoff_proofs(proofs)
        return ContentProofAuditSnapshot(
            build_id=build_id,
            release_id=str(release["id"]),
            passed_item_ids=tuple(
                item_id for item_id in item_order if item_id in passed
            ),
            repairable_item_ids=tuple(
                item_id for item_id in item_order if item_id in repairable
            ),
            terminal_failed_item_ids=tuple(
                item_id for item_id in item_order if item_id in terminal_failed
            ),
        )

    def audit_content_parent_retry_authority(
        self,
        *,
        inventory: Mapping[str, object],
    ) -> ContentParentRetryAuditSnapshot:
        """Project retry facts only after replaying Task-7 authority.

        The caller owns the transaction and chooses ordinary SELECTs or the
        formal catalog lock order.  This projection is deliberately pure: it
        neither opens a transaction nor issues SQL, so parent GET remains
        SELECT-only while parent POST can pass the same locked inventory.
        """
        raw_build = inventory.get("build")
        raw_release = inventory.get("release")
        raw_dispatches = inventory.get("dispatches")
        build = raw_build if isinstance(raw_build, Mapping) else {}
        release = raw_release if isinstance(raw_release, Mapping) else {}
        dispatches = (
            [row for row in raw_dispatches if isinstance(row, Mapping)]
            if isinstance(raw_dispatches, Sequence)
            else []
        )
        dispatch_ids = tuple(str(row.get("id") or "") for row in dispatches)
        open_ids = tuple(
            str(row.get("id") or "")
            for row in dispatches
            if str(row.get("status") or "") in {"dispatched", "ambiguous"}
        )
        failed_safe_ids = tuple(
            str(row.get("id") or "")
            for row in dispatches
            if str(row.get("status") or "") == "failed_safe"
        )
        raw_error = build.get("error_code")
        build_error = (
            re.sub(
                r"[^a-z0-9_.-]",
                "_",
                str(raw_error).lower(),
            )[:128]
            if raw_error is not None
            else None
        )

        def snapshot(
            authority_class: Literal[
                "pre_provider_dependency",
                "host_only_dependency",
                "not_replayable",
            ],
            *,
            graph_complete: bool = False,
        ) -> ContentParentRetryAuditSnapshot:
            return ContentParentRetryAuditSnapshot(
                build_id=str(build.get("id") or ""),
                release_id=str(release.get("id") or ""),
                authority_class=authority_class,
                provider_dispatch_ids=dispatch_ids,
                open_or_ambiguous_dispatch_ids=open_ids,
                failed_safe_dispatch_ids=failed_safe_ids,
                provider_graph_complete=graph_complete,
                next_work_kind=(
                    "host_gate" if authority_class == "host_only_dependency" else None
                ),
                build_error_code=build_error,
            )

        raw_items = inventory.get("items")
        raw_histories = inventory.get("attemptHistoriesByItem")
        raw_historical_fingerprints = inventory.get(
            "historicalQuestionFingerprintsByItem"
        )
        if (
            not self._parent_retry_catalog_authority_is_exact(inventory)
            or not isinstance(raw_items, Sequence)
            or not isinstance(raw_histories, Mapping)
            or not isinstance(raw_historical_fingerprints, Mapping)
            or not isinstance(raw_dispatches, Sequence)
            or len(dispatches) != len(raw_dispatches)
            or any(not value for value in dispatch_ids)
            or len(set(dispatch_ids)) != len(dispatch_ids)
        ):
            return snapshot("not_replayable")
        items = [row for row in raw_items if isinstance(row, Mapping)]
        histories = {
            str(item_id): attempts
            for item_id, attempts in raw_histories.items()
            if isinstance(attempts, Mapping)
        }
        historical_fingerprints = {
            str(item_id): attempts
            for item_id, attempts in raw_historical_fingerprints.items()
            if isinstance(attempts, Mapping)
        }
        if (
            len(histories) != len(raw_histories)
            or len(historical_fingerprints)
            != len(raw_historical_fingerprints)
        ):
            return snapshot("not_replayable")
        try:
            audit = self._audit_locked_content_inventory(
                conn=None,
                inventory=inventory,
                authority_prevalidated=True,
            )
        except Exception:
            return snapshot("not_replayable")
        passed = frozenset(str(value) for value in audit["passedItemIds"])
        repairable = frozenset(
            str(value) for value in audit["repairableItemIds"]
        )
        terminal = any(
            str(item.get("status") or "") == "failed"
            and str(item.get("id") or "") not in repairable
            for item in items
        )
        deterministic = bool(build_error or repairable or terminal)
        if not dispatches and not deterministic:
            pristine = all(
                str(item.get("status") or "") == "pending"
                and type(item.get("attempt_count")) is int
                and int(item["attempt_count"]) == 0
                and str(item.get("content_phase") or "") == "not_started"
                and str(item.get("content_gate_status") or "")
                == "not_started"
                and not self._parent_retry_history_has_residue(
                    histories.get(str(item.get("id") or ""))
                )
                for item in items
            )
            if pristine:
                return snapshot("pre_provider_dependency")
            return snapshot("not_replayable")
        if deterministic or open_ids or failed_safe_ids or not dispatches:
            return snapshot("not_replayable")
        if any(str(row.get("status") or "") != "succeeded" for row in dispatches):
            return snapshot("not_replayable")
        host_items = [
            item
            for item in items
            if str(item.get("status") or "") == "processing"
            and str(item.get("content_phase") or "")
            in {"host_gate_pending", "host_gate_running"}
        ]
        if len(host_items) != 1:
            return snapshot("not_replayable")
        host_item = host_items[0]
        host_id = str(host_item.get("id") or "")
        if any(
            not (
                str(item.get("id") or "") in passed
                and str(item.get("status") or "") == "course_ready"
            )
            and not (
                str(item.get("id") or "") == host_id
                and str(item.get("status") or "") == "processing"
            )
            and not (
                str(item.get("status") or "") == "pending"
                and type(item.get("attempt_count")) is int
                and int(item["attempt_count"]) == 0
                and str(item.get("content_phase") or "") == "not_started"
                and str(item.get("content_gate_status") or "")
                == "not_started"
                and not self._parent_retry_history_has_residue(
                    histories.get(str(item.get("id") or ""))
                )
            )
            for item in items
        ):
            return snapshot("not_replayable")
        prior_rows = [
            item
            for item in items
            if str(item.get("subject") or "")
            == str(host_item.get("subject") or "")
            and str(item.get("skill_id") or "")
            == str(host_item.get("skill_id") or "")
            and str(item.get("boundary_version") or "")
            == str(host_item.get("boundary_version") or "")
            and int(item.get("variant_ordinal") or 0)
            < int(host_item.get("variant_ordinal") or 0)
        ]
        prior_rows.sort(key=lambda value: int(value["variant_ordinal"]))
        evidence = {
            "item": dict(host_item),
            "attemptHistories": histories.get(host_id, {}),
            "historicalQuestionFingerprintsByAttempt": (
                historical_fingerprints.get(host_id, {})
            ),
        }
        prior_evidence = tuple(
            {
                "item": dict(item),
                "attemptHistories": histories.get(str(item["id"]), {}),
                "historicalQuestionFingerprintsByAttempt": (
                    historical_fingerprints.get(str(item["id"]), {})
                ),
            }
            for item in prior_rows
        )
        try:
            graph = self.audit_content_host_retry_graph(
                evidence=evidence,
                prior_evidence=prior_evidence,
            )
        except Exception:
            return snapshot("not_replayable")
        authenticated_ids: list[str] = []
        authenticated_item_ids = set(passed) | {host_id}
        for item_id in authenticated_item_ids:
            attempts = histories.get(item_id)
            if not isinstance(attempts, Mapping):
                return snapshot("not_replayable")
            for attempt in (1, 2):
                history = attempts.get(attempt)
                if not isinstance(history, Mapping):
                    return snapshot("not_replayable")
                raw_attempt_dispatches = history.get("dispatches")
                if not isinstance(raw_attempt_dispatches, Sequence):
                    return snapshot("not_replayable")
                for row in raw_attempt_dispatches:
                    if not isinstance(row, Mapping):
                        return snapshot("not_replayable")
                    authenticated_ids.append(str(row.get("id") or ""))
        if (
            tuple(authenticated_ids)
            and set(authenticated_ids) == set(dispatch_ids)
            and len(authenticated_ids) == len(dispatch_ids)
            and graph.item_id == host_id
            and graph.logical_attempt == int(host_item.get("attempt_count") or 0)
        ):
            return snapshot("host_only_dependency", graph_complete=True)
        return snapshot("not_replayable")

    def audit_content_provider_dependency_retry(
        self,
        *,
        evidence: Mapping[str, object],
        content_phase: str,
    ) -> ContentProviderDependencyAuditSnapshot:
        """Seal one exact item history after Task-7 released Provider lease."""
        item = evidence.get("item") if isinstance(evidence, Mapping) else None
        if not isinstance(item, Mapping):
            raise ValueError("Provider dependency item is missing")
        item_id = str(item.get("id") or "")
        logical_attempt = item.get("attempt_count")
        if (
            not item_id
            or type(logical_attempt) is not int
            or logical_attempt not in {1, 2}
            or str(item.get("status") or "") != "processing"
            or str(item.get("content_phase") or "") != content_phase
            or content_phase not in {
                str(authority["phase"]) for authority in QUESTION_PHASE_IO
            }
        ):
            raise ValueError("Provider dependency item authority drift")
        current = self._locked_attempt_history(
            evidence=evidence,
            attempt=logical_attempt,
        )
        dispatches = current.get("dispatches")
        if not isinstance(dispatches, Sequence) or any(
            not isinstance(row, Mapping) for row in dispatches
        ):
            raise ValueError("Provider dependency dispatch history drift")
        if any(
            current.get(key)
            for key in ("jobs", "candidates", "courses")
        ):
            raise ValueError("Provider dependency persistence residue")
        phase_ordinal = self._content_phase_ordinal(content_phase)
        checkpoints: dict[tuple[str, int], Mapping[str, object]] = {}
        ordered: list[tuple[str, int]] = []
        request_id = str(item.get("active_generation_request_id") or "")
        for row in dispatches:
            phase = str(row.get("phase") or "")
            ordinal = row.get("phase_ordinal")
            if (
                type(ordinal) is not int
                or ordinal >= phase_ordinal
                or self._content_phase_ordinal(phase) != ordinal
                or str(row.get("status") or "") != "succeeded"
                or str(row.get("build_item_id") or "") != item_id
                or row.get("logical_attempt") != logical_attempt
                or str(row.get("generation_request_id") or "") != request_id
                or row.get("attempt_started_at")
                != item.get("content_attempt_started_at")
                or row.get("attempt_hard_deadline_at")
                != item.get("content_provider_attempt_hard_deadline_at")
            ):
                raise ValueError("Provider dependency phase gap drift")
            execution = question_phase_execution_authority(phase, ordinal)
            expected_profile = self._content_profile_evidence(
                str(execution["providerRole"])
            )
            checkpoint = self._decode_content_json(row.get("checkpoint_json"))
            output_hash = hashlib.sha256(
                self._canonical_content_json(checkpoint).encode("utf-8")
            ).hexdigest()
            if (
                str(row.get("provider") or "") != expected_profile.name
                or str(row.get("model") or "") != expected_profile.model
                or str(row.get("profile") or "") != expected_profile.profile_hash
                or str(row.get("output_sha256") or "") != output_hash
            ):
                raise ValueError("Provider dependency checkpoint drift")
            checkpoints[(phase, ordinal)] = checkpoint
            ordered.append((phase, ordinal))
        if self._executed_content_chain(checkpoints) != ordered:
            raise ValueError("Provider dependency branch chain drift")
        expected_next = (
            ("outline", 1)
            if not ordered
            else self._next_content_phase(
                phase=ordered[-1][0],
                ordinal=ordered[-1][1],
                checkpoint=checkpoints[ordered[-1]],
            )
        )
        if expected_next != (content_phase, phase_ordinal):
            raise ValueError("Provider dependency next phase drift")
        if logical_attempt == 1:
            self._require_empty_locked_attempt_history(evidence=evidence, attempt=2)
        elif recovery_dispatches(item=item, evidence=evidence) is not None:
            # This exact returned failure has no rejected course persistence;
            # the immutable operator receipt binds its original dispatch graph.
            pass
        else:
            attempt_one = self._locked_attempt_evidence(
                evidence=evidence,
                attempt=1,
            )
            rejected_job = attempt_one.get("job")
            rejected_candidate = attempt_one.get("candidate")
            rejected_course = attempt_one.get("course")
            expected_attempt_one_request = str(
                item.get("generation_request_id") or ""
            )
            if not (
                isinstance(rejected_job, Mapping)
                and isinstance(rejected_candidate, Mapping)
                and isinstance(rejected_course, Mapping)
                and str(rejected_job.get("request_id") or "")
                == expected_attempt_one_request
                and str(rejected_job.get("status") or "") == "failed"
                and str(rejected_candidate.get("status") or "") == "rejected"
                and rejected_candidate.get("published_at") is None
                and str(rejected_candidate.get("job_id") or "")
                == str(rejected_job.get("id") or "")
                and str(rejected_candidate.get("course_id") or "")
                == str(rejected_course.get("id") or "")
                and str(rejected_candidate.get("course_version") or "")
                == str(rejected_course.get("version") or "")
            ):
                raise ValueError("Provider dependency rejected persistence drift")
            historical_dispatches = attempt_one.get("dispatches")
            if not isinstance(historical_dispatches, Sequence):
                raise ValueError("Provider dependency rejected history drift")
            historical_deadlines = {
                (
                    row.get("attempt_started_at"),
                    row.get("attempt_hard_deadline_at"),
                )
                for row in historical_dispatches
                if isinstance(row, Mapping)
            }
            if len(historical_deadlines) != 1:
                raise ValueError("Provider dependency rejected deadline drift")
            historical_start, historical_deadline = next(iter(historical_deadlines))
            if (
                type(historical_start) is not int
                or historical_start <= 0
                or type(historical_deadline) is not int
                or not provider_attempt_deadline_is_valid(
                    historical_start, historical_deadline
                )
            ):
                raise ValueError("Provider dependency rejected deadline drift")
            for row in historical_dispatches:
                if not isinstance(row, Mapping):
                    raise ValueError("Provider dependency rejected profile drift")
                phase = str(row.get("phase") or "")
                ordinal = row.get("phase_ordinal")
                if type(ordinal) is not int:
                    raise ValueError("Provider dependency rejected profile drift")
                execution = question_phase_execution_authority(phase, ordinal)
                expected_profile = self._content_profile_evidence(
                    str(execution["providerRole"])
                )
                if (
                    str(row.get("provider") or "") != expected_profile.name
                    or str(row.get("model") or "") != expected_profile.model
                    or str(row.get("profile") or "")
                    != expected_profile.profile_hash
                ):
                    raise ValueError("Provider dependency rejected profile drift")
            historical_item = {
                **dict(item),
                "attempt_count": 1,
                "active_generation_request_id": str(
                    item.get("generation_request_id") or ""
                ),
                "content_attempt_started_at": historical_start,
                "content_provider_attempt_hard_deadline_at": historical_deadline,
            }
            historical_graph, historical_checkpoints = (
                self._validated_content_dispatch_graph(
                    item=historical_item,
                    dispatches=historical_dispatches,
                )
            )
            final_checkpoint = historical_checkpoints.get(
                (historical_graph.final_phase, historical_graph.final_phase_ordinal)
            )
            final_key = question_phase_execution_authority(
                historical_graph.final_phase,
                historical_graph.final_phase_ordinal,
            )["finalCandidateKey"]
            candidate_course = (
                final_checkpoint.get(final_key)
                if isinstance(final_checkpoint, Mapping)
                and isinstance(final_key, str)
                else None
            )
            if not isinstance(candidate_course, Mapping):
                raise ValueError("Provider dependency rejected course drift")
            generator_profile = self._content_profile_evidence("generator")
            verifier_profile = self._content_profile_evidence("verifier")
            historical_host_evidence = QuestionPhaseCourseEvidence(
                final_phase=historical_graph.final_phase,
                final_phase_ordinal=historical_graph.final_phase_ordinal,
                candidate_course=candidate_course,
                question_fingerprints=final_checkpoint.get(
                    "questionFingerprints"
                ),
                validation=final_checkpoint.get("validation"),
                independent_solution=final_checkpoint.get(
                    "independentSolution"
                ),
                generator_profile=generator_profile,
                verifier_profile=verifier_profile,
                existing_fingerprint_count=int(
                    final_checkpoint.get("validation", {}).get(
                        "existingFingerprintsChecked", -1
                    )
                ),
                authoritative_existing_fingerprints=tuple(
                    attempt_one.get("historicalQuestionFingerprints") or ()
                ),
            )
            historical_target = self._content_target(historical_item)
            historical_identity = PrimaryOneHostGateIdentity(
                catalog_item_id=str(historical_item["id"]),
                logical_attempt=1,
                generation_request_id=str(
                    historical_item["active_generation_request_id"]
                ),
                course_id=str(candidate_course.get("id") or ""),
                course_version=str(candidate_course.get("version") or ""),
                curriculum_version=PRIMARY_CURRICULUM_VERSION,
                content_validation_contract_version=formal_content_validation_identity(historical_target.grade_code)["contentValidationContractVersion"],
                content_validation_dataset_sha256=formal_content_validation_identity(historical_target.grade_code)["contentValidationDatasetSha256"],
                subject_language_policy_version=(
                    SUBJECT_LANGUAGE_POLICY_VERSION
                ),
                generator_profile_hash=generator_profile.profile_hash,
                verifier_profile_hash=verifier_profile.profile_hash,
            )
            self._validate_locked_generation_persistence(
                evidence=attempt_one,
                item=historical_item,
                candidate_course=candidate_course,
                expected_job_status="failed",
                expected_candidate_status="rejected",
            )
            candidate = attempt_one.get("candidate")
            envelope = self._decode_content_json(
                candidate.get("validation_json")
                if isinstance(candidate, Mapping)
                else None
            )
            receipt = envelope.get("hostGateReceipt")
            receipt_hash = envelope.get("hostGateReceiptHash")
            expected_receipt_hash = (
                hashlib.sha256(
                    self._canonical_content_json(receipt).encode("utf-8")
                ).hexdigest()
                if isinstance(receipt, Mapping)
                else ""
            )
            receipt_validator = self.primary_one_host_validator
            receipt_shape_authority = getattr(
                receipt_validator,
                "_assert_primary_one_receipt_shape",
                None,
            )
            if not callable(receipt_shape_authority):
                receipt_shape_authority = getattr(
                    getattr(receipt_validator, "delegate", None),
                    "_assert_primary_one_receipt_shape",
                    None,
                )
            try:
                if not callable(receipt_shape_authority):
                    raise PrimaryOneHostGateControlError(
                        "Host receipt shape authority is unavailable"
                    )
                receipt_shape_authority(receipt)
            except PrimaryOneHostGateControlError as exc:
                raise ValueError(
                    "Provider dependency rejected receipt drift"
                ) from exc
            receipt_base_authority = getattr(
                receipt_validator,
                "_primary_one_receipt_base",
                None,
            )
            if not callable(receipt_base_authority):
                receipt_base_authority = getattr(
                    getattr(receipt_validator, "delegate", None),
                    "_primary_one_receipt_base",
                    None,
                )
            if not callable(receipt_base_authority):
                raise ValueError(
                    "Provider dependency receipt identity authority unavailable"
                )
            expected_receipt_base = receipt_base_authority(
                target=historical_target,
                identity=historical_identity,
                evidence=historical_host_evidence,
                skill_boundary_sha256=hashlib.sha256(
                    self._canonical_content_json(
                        self._content_boundary(historical_item)
                    ).encode("utf-8")
                ).hexdigest(),
                candidate_course_sha256=hashlib.sha256(
                    self._canonical_content_json(candidate_course).encode(
                        "utf-8"
                    )
                ).hexdigest(),
                sidecar_evidence_sha256=hashlib.sha256(
                    self._canonical_content_json(
                        {
                            "questionFingerprints": (
                                historical_host_evidence.question_fingerprints
                            ),
                            "validation": historical_host_evidence.validation,
                            "independentSolution": (
                                historical_host_evidence.independent_solution
                            ),
                        }
                    ).encode("utf-8")
                ).hexdigest(),
            )
            if any(
                receipt.get(key) != value
                for key, value in expected_receipt_base.items()
            ):
                raise ValueError("Provider dependency rejected receipt identity drift")
            receipt_fingerprint = receipt.get("hostContentFingerprint")
            envelope_fingerprint = envelope.get("contentFingerprint")
            if (
                set(envelope)
                != {
                    "schemaVersion",
                    "contentFingerprint",
                    "hostGateReceipt",
                    "hostGateReceiptHash",
                }
                or str(envelope.get("schemaVersion") or "")
                != formal_content_validation_identity(historical_target.grade_code)["hostGateEvidenceSchemaVersion"]
                or not isinstance(receipt, Mapping)
                or str(receipt.get("outcome") or "") != "rejected"
                or not isinstance(envelope_fingerprint, str)
                or envelope_fingerprint != receipt_fingerprint
                or not isinstance(receipt_fingerprint, str)
                or (
                    bool(receipt_fingerprint)
                    and re.fullmatch(r"[0-9a-f]{64}", receipt_fingerprint)
                    is None
                )
                or not re.fullmatch(r"[0-9a-f]{64}", str(receipt_hash or ""))
                or str(receipt_hash) != expected_receipt_hash
            ):
                raise ValueError("Provider dependency rejected receipt drift")
        return ContentProviderDependencyAuditSnapshot(
            build_id=str(item.get("build_job_id") or ""),
            release_id=str(item.get("release_id") or ""),
            item_id=item_id,
            logical_attempt=logical_attempt,
            content_phase=content_phase,
            predecessor_dispatch_ids=tuple(
                str(row["id"]) for row in dispatches
            ),
            predecessor_final_phase=(ordered[-1][0] if ordered else None),
            predecessor_final_phase_ordinal=(
                ordered[-1][1] if ordered else None
            ),
        )

    def audit_content_host_dependency_retry(
        self,
        *,
        evidence: Mapping[str, object],
    ) -> ContentHostDependencyAuditSnapshot:
        """Seal one exact Host-bound item without reading unrelated priors."""
        item = evidence.get("item") if isinstance(evidence, Mapping) else None
        if not isinstance(item, Mapping):
            raise ValueError("Host dependency item is missing")
        attempt = item.get("attempt_count")
        if (
            type(attempt) is not int
            or attempt not in {1, 2}
            or str(item.get("content_phase") or "") != "host_gate_running"
            or str(item.get("content_gate_status") or "") != "retry_wait"
            or not self._host_retry_item_authority_is_exact(
                item=item,
                attempt=attempt,
            )
        ):
            raise ValueError("Host dependency item authority drift")
        if attempt == 1:
            self._require_empty_locked_attempt_history(
                evidence=evidence,
                attempt=2,
            )
            attempt_one = None
        else:
            histories = evidence.get("attemptHistories")
            if not isinstance(histories, Mapping):
                raise ValueError("Host dependency attempt history drift")
            synthetic_histories = {
                1: histories.get(1),
                2: {
                    "requestId": str(item.get("generation_request_id") or "")
                    + ".attempt2",
                    "dispatches": [],
                    "jobs": [],
                    "candidates": [],
                    "courses": [],
                },
            }
            self.audit_content_provider_dependency_retry(
                evidence={
                    "item": {
                        **dict(item),
                        "content_phase": "outline",
                    },
                    "attemptHistories": synthetic_histories,
                    "historicalQuestionFingerprintsByAttempt": evidence.get(
                        "historicalQuestionFingerprintsByAttempt"
                    ),
                },
                content_phase="outline",
            )
            attempt_one = self._locked_attempt_evidence(
                evidence=evidence,
                attempt=1,
            )
        current = self._locked_host_pending_attempt_evidence(
            evidence=evidence,
            attempt=attempt,
        )
        dispatches = current.get("dispatches")
        if not isinstance(dispatches, Sequence):
            raise ValueError("Host dependency dispatch history drift")
        graph, checkpoints = self._validated_content_dispatch_graph(
            item=item,
            dispatches=dispatches,
        )
        for row in dispatches:
            if not isinstance(row, Mapping):
                raise ValueError("Host dependency dispatch profile drift")
            phase = str(row.get("phase") or "")
            ordinal = row.get("phase_ordinal")
            if type(ordinal) is not int:
                raise ValueError("Host dependency dispatch profile drift")
            execution = question_phase_execution_authority(phase, ordinal)
            expected_profile = self._content_profile_evidence(
                str(execution["providerRole"])
            )
            if (
                str(row.get("provider") or "") != expected_profile.name
                or str(row.get("model") or "") != expected_profile.model
                or str(row.get("profile") or "")
                != expected_profile.profile_hash
            ):
                raise ValueError("Host dependency dispatch profile drift")
        final_checkpoint = checkpoints.get(
            (graph.final_phase, graph.final_phase_ordinal)
        )
        final_key = question_phase_execution_authority(
            graph.final_phase,
            graph.final_phase_ordinal,
        )["finalCandidateKey"]
        candidate_course = (
            final_checkpoint.get(final_key)
            if isinstance(final_checkpoint, Mapping)
            and isinstance(final_key, str)
            else None
        )
        if not isinstance(candidate_course, Mapping):
            raise ValueError("Host dependency candidate course drift")
        self._validate_locked_host_pending_persistence(
            evidence=current,
            item=item,
            candidate_course=candidate_course,
            attempt_one_evidence=attempt_one,
        )
        return ContentHostDependencyAuditSnapshot(
            build_id=str(item.get("build_job_id") or ""),
            release_id=str(item.get("release_id") or ""),
            item_id=str(item.get("id") or ""),
            logical_attempt=attempt,
            content_phase="host_gate_running",
            dispatch_ids=graph.dispatch_ids,
        )

    @staticmethod
    def _parent_retry_history_has_residue(raw: object) -> bool:
        if raw is None:
            return False
        if not isinstance(raw, Mapping):
            return True
        for attempt in (1, 2):
            history = raw.get(attempt)
            if not isinstance(history, Mapping):
                return True
            for key in ("dispatches", "jobs", "candidates", "courses"):
                rows = history.get(key)
                if not isinstance(rows, Sequence) or bool(rows):
                    return True
        return False

    def _parent_retry_catalog_authority_is_exact(
        self, inventory: Mapping[str, object]
    ) -> bool:
        plan = inventory.get("plan")
        release = inventory.get("release")
        build = inventory.get("build")
        raw_items = inventory.get("items")
        if (
            not isinstance(plan, Mapping)
            or not isinstance(release, Mapping)
            or not isinstance(build, Mapping)
            or not isinstance(raw_items, Sequence)
            or inventory.get("releaseHasCatalogItems") is not False
        ):
            return False
        items = [item for item in raw_items if isinstance(item, Mapping)]
        try:
            target = canonical_preparation_target_for(plan)
        except (ValueError, TypeError, KeyError):
            return False
        if len(items) != formal_target_course_count(target) or len(items) != len(raw_items):
            return False
        target_json = self._canonical_content_json(target)
        target_fingerprint = preparation_target_fingerprint(target)
        expected_request_id = f"grade-build:{target_fingerprint}"
        request_id = str(build.get("request_id") or "")
        request_digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[
            :24
        ]
        build_id = f"catalog_build_{request_digest}"
        release_id = f"catalog_release_{request_digest}"
        exact_int_fields = (
            (build, "total_item_count", formal_target_course_count(plan)),
            (build, "ready_item_count", 0),
            (build, "failed_item_count", 0),
            (release, "required_boundary_count", int(target["boundaryCount"])),
            (release, "ready_item_count", 0),
        )
        if any(
            type(owner.get(field)) is not int or int(owner[field]) != expected
            for owner, field, expected in exact_int_fields
        ):
            return False
        if not (
            request_id == expected_request_id
            and str(plan.get("shared_build_request_id") or "") == request_id
            and str(plan.get("catalog_build_id") or "") == build_id
            and str(plan.get("catalog_release_id") or "") == release_id
            and str(plan.get("target_fingerprint") or "")
            == target_fingerprint
            and str(plan.get("grade_code") or "") == preparation_authority_grade(plan)
            and str(plan.get("curriculum_version") or "")
            == str(target["curriculumVersion"])
            and (
                self._canonical_content_json(plan["target_spec_json"])
                if isinstance(plan.get("target_spec_json"), Mapping)
                else str(plan.get("target_spec_json") or "")
            )
            == target_json
            and str(build.get("id") or "") == build_id
            and str(build.get("release_id") or "") == release_id
            and str(release.get("id") or "") == release_id
            and str(build.get("execution_mode") or "") == "content_only"
            and str(build.get("stage_ceiling") or "") == "content_ready"
            and str(build.get("status") or "") in {"queued", "running"}
            and str(build.get("curriculum_version") or "")
            == str(target["curriculumVersion"])
            and str(build.get("target_spec_json") or "") == target_json
            and str(build.get("content_manifest_version") or "")
            == str(target["schemaVersion"])
            and str(build.get("canary_manifest_json") or "")
            == self._canonical_content_json(target["canaryManifest"])
            and build.get("error_code") is None
            and build.get("error_message_safe") is None
            and build.get("completed_at") is None
            and str(release.get("status") or "") == "draft"
            and str(release.get("quality_status") or "") == "building"
            and str(release.get("curriculum_version") or "")
            == str(target["curriculumVersion"])
            and release.get("activated_at") is None
            and release.get("retired_at") is None
        ):
            return False
        expected = self.repository._expected_content_item_immutables(
            build_id=build_id,
            release_id=release_id,
            curriculum_version=str(target["curriculumVersion"]),
            content_manifest_version=str(target["schemaVersion"]),
            course_targets=target["courseTargets"],
            grade_code=preparation_authority_grade(target),
        )
        if any(
            not self.repository._content_item_immutables_match(row, immutable)
            for row, immutable in zip(items, expected)
        ):
            return False
        return all(
            type(row.get("package_attempt_count")) is int
            and int(row["package_attempt_count"]) == 0
            and row.get("active_package_request_id") is None
            and row.get("package_id") is None
            and row.get("package_version") is None
            for row in items
        )

    def _bind_content_work_unit_or_cleanup(
        self,
        *,
        build_id: str,
        action: str,
        item: Mapping[str, object],
        summary: Mapping[str, object],
        bind_work_unit: Callable[[ContentWorkUnitClaim], bool] | None,
    ) -> ContentAdvanceResult | None:
        if bind_work_unit is None:
            return None
        try:
            claim = ContentWorkUnitClaim(
                build_id=build_id,
                item_id=str(item["id"]),
                item_lease_token=str(item["content_lease_token"]),
                logical_attempt=int(item["attempt_count"]),
                content_phase=str(item["content_phase"]),
                work_unit_kind=(
                    "host_gate" if action == "host" else "provider_phase"
                ),
                work_unit_deadline_at=int(
                    item["content_work_unit_deadline_at"]
                ),
            )
            accepted = bind_work_unit(claim) is True
        except Exception:
            accepted = False
        if accepted:
            return None

        cleanup_result: object = False
        cleanup_now = self._trusted_content_now()
        try:
            with self.repository.transaction() as conn:
                if action == "provider":
                    cleanup_result = self.repository.release_content_provider_dependency(
                        conn,
                        item_id=str(item["id"]),
                        lease_token=str(item["content_lease_token"]),
                        now=cleanup_now,
                    )
                else:
                    cleanup_result = self.repository.release_content_host_dependency(
                        conn,
                        build_id=build_id,
                        item_id=str(item["id"]),
                        logical_attempt=int(item["attempt_count"]),
                        generation_request_id=str(
                            item["active_generation_request_id"]
                        ),
                        gate_ordinal=int(item["content_gate_attempt_count"]),
                        lease_token=str(item["content_lease_token"]),
                        work_deadline_at=int(
                            item["content_work_unit_deadline_at"]
                        ),
                        now=cleanup_now,
                    )
        except Exception:
            cleanup_result = False
        if cleanup_result == "failed":
            return ContentAdvanceResult(
                "failed",
                build_id,
                str(item["id"]),
                self._content_summary_after_transition(
                    build_id, terminal_already_fenced=True
                ),
            )
        return ContentAdvanceResult(
            "stale", build_id, str(item["id"]), summary
        )

    def _advance_content_attempt_two_after_authorization(
        self,
        *,
        build_id: str,
        expected_item_id: str,
        summary: Mapping[str, object],
        authorize_control_work: Callable[[], bool] | None,
    ) -> ContentAdvanceResult:
        if authorize_control_work is not None:
            try:
                if authorize_control_work() is not True:
                    return ContentAdvanceResult(
                        "stale", build_id, expected_item_id, summary
                    )
            except Exception:
                return ContentAdvanceResult(
                    "stale", build_id, expected_item_id, summary
                )

        now = self._trusted_content_now()
        with self.repository.transaction() as conn:
            try:
                inventory = self.repository.load_content_proof_inventory(
                    conn, build_id=build_id
                )
                audit = self._audit_locked_content_inventory(
                    conn=conn,
                    inventory=inventory,
                )
                plan = self.repository.prepare_content_advance(
                    conn,
                    build_id=build_id,
                    now=now,
                    passed_item_ids=audit["passedItemIds"],
                    repairable_item_ids=audit["repairableItemIds"],
                    locked_attempt_histories_by_item=inventory.get(
                        "attemptHistoriesByItem", {}
                    ),
                )
            except (
                PrimaryOneHostGateControlError,
                PrimaryOneHostGateDependencyError,
                KeyError,
                TypeError,
                ValueError,
            ):
                return ContentAdvanceResult(
                    "stale", build_id, expected_item_id, summary
                )
            item = plan.get("item")
            if (
                str(plan.get("action") or "") != "attempt2"
                or not isinstance(item, Mapping)
                or str(item.get("id") or "") != expected_item_id
            ):
                return ContentAdvanceResult(
                    "stale", build_id, expected_item_id, audit["summary"]
                )
            locked_evidence = audit["evidenceByItem"].get(expected_item_id)
            if not isinstance(locked_evidence, Mapping):
                return ContentAdvanceResult(
                    "stale", build_id, expected_item_id, audit["summary"]
                )
            locked_plan = {
                **dict(plan),
                "contentSummary": audit["summary"],
                "attemptOneEvidence": locked_evidence,
            }
            return self._authorize_content_attempt_two(
                build_id=build_id,
                plan=locked_plan,
                item=item,
                summary=audit["summary"],
                conn=conn,
            )

    def _validate_content_handoff(self, plan: Mapping[str, object]) -> None:
        proofs = self._accepted_content_proofs(plan.get("allPassedEvidence"))
        self._validate_content_handoff_proofs(proofs)

    def _validate_content_handoff_proofs(
        self,
        proofs: Sequence[AcceptedPrimaryOneHostReceipt],
    ) -> None:
        if not proofs or any(not isinstance(proof, AcceptedPrimaryOneHostReceipt) for proof in proofs):
            raise ValueError("content handoff requires typed formal proofs")
        grade_code = proofs[0].target.grade_code
        target = build_preparation_target(grade_code)
        if len(proofs) != formal_target_course_count(grade_code) or any(proof.target.grade_code != grade_code for proof in proofs):
            raise ValueError("content handoff grade or cardinality drift")
        groups: dict[
            tuple[str, str, str], list[PrimaryOneValidatedVariant]
        ] = {}
        for proof in proofs:
            self.primary_one_host_validator.validate_primary_one_accepted_receipt(
                proof
            )
            key = (
                proof.target.subject,
                proof.target.skill_id,
                proof.target.boundary_version,
            )
            groups.setdefault(key, []).append(
                PrimaryOneValidatedVariant(
                    target=proof.target,
                    immutable_course=proof.immutable_course,
                    receipt=proof.receipt,
                    receipt_hash=proof.receipt_hash,
                )
            )
        if len(groups) != int(target["boundaryCount"]) or any(len(values) != 3 for values in groups.values()):
            raise ValueError("content handoff variant inventory drift")
        for variants in groups.values():
            self.catalog_validator.validate_primary_one_variant_set(variants)

    def _audit_locked_content_inventory(
        self,
        *,
        conn: object | None,
        inventory: Mapping[str, object],
        authority_prevalidated: bool = False,
    ) -> Mapping[str, object]:
        release = inventory.get("release")
        build = inventory.get("build")
        raw_items = inventory.get("items")
        raw_evidence = inventory.get("evidence")
        if (
            not isinstance(release, Mapping)
            or not isinstance(build, Mapping)
            or not isinstance(raw_items, Sequence)
            or not isinstance(raw_evidence, Sequence)
        ):
            raise ValueError("locked content proof inventory is incomplete")
        items = [item for item in raw_items if isinstance(item, Mapping)]
        evidence_rows = [
            evidence for evidence in raw_evidence if isinstance(evidence, Mapping)
        ]
        if len(items) != formal_target_course_count(build) or len(evidence_rows) != len(raw_evidence):
            raise ValueError("locked content proof inventory shape drift")
        if not authority_prevalidated and not self.repository._content_authority_is_exact(
            conn,
            release=release,
            build=build,
            rows=items,
            allow_terminal=str(build.get("status") or "") == "failed",
        ):
            raise ValueError("locked content build authority drift")
        by_item = {
            str(evidence["item"]["id"]): evidence
            for evidence in evidence_rows
            if isinstance(evidence.get("item"), Mapping)
        }
        if len(by_item) != len(evidence_rows):
            raise ValueError("locked content evidence identity drift")

        proofs: list[AcceptedPrimaryOneHostReceipt] = []
        proof_evidence: dict[tuple[str, str, str, int], Mapping[str, object]] = {}
        passed_ids: set[str] = set()
        repairable_ids: set[str] = set()
        for item in sorted(
            items,
            key=lambda value: (
                int(value.get("subject_ordinal") or 0),
                int(value.get("boundary_ordinal") or 0),
                int(value.get("variant_ordinal") or 0),
                str(value.get("id") or ""),
            ),
        ):
            status = str(item.get("status") or "")
            if status not in {"course_ready", "failed"}:
                continue
            evidence = by_item.get(str(item.get("id") or ""))
            if evidence is None:
                raise ValueError("locked content proof is missing")
            boundary_key = (
                str(item.get("subject") or ""),
                str(item.get("skill_id") or ""),
                str(item.get("boundary_version") or ""),
            )
            variant_ordinal = int(item.get("variant_ordinal") or 0)
            priors = [
                proof_evidence[(*boundary_key, prior)]
                for prior in range(1, variant_ordinal)
                if (*boundary_key, prior) in proof_evidence
            ]
            if len(priors) != max(0, variant_ordinal - 1):
                raise ValueError("locked prior content proof drift")
            if status == "course_ready":
                proof = self._validate_locked_passed_evidence(
                    evidence=evidence,
                    prior_evidence=priors,
                )
                proofs.append(proof)
                passed_ids.add(str(item["id"]))
                proof_evidence[(*boundary_key, variant_ordinal)] = evidence
                if variant_ordinal == 3:
                    variants = [
                        PrimaryOneValidatedVariant(
                            target=value.target,
                            immutable_course=value.immutable_course,
                            receipt=value.receipt,
                            receipt_hash=value.receipt_hash,
                        )
                        for value in proofs
                        if (
                            value.target.subject,
                            value.target.skill_id,
                            value.target.boundary_version,
                        )
                        == boundary_key
                    ]
                    if len(variants) != 3:
                        raise ValueError("locked three-variant proof drift")
                    self.catalog_validator.validate_primary_one_variant_set(
                        variants
                    )
            elif (
                int(item.get("attempt_count") or 0) == 1
                and str(item.get("content_gate_status") or "")
                == "failed_deterministic"
            ):
                self._validate_locked_rejected_evidence(
                    evidence=evidence,
                    prior_evidence=priors,
                )
                repairable_ids.add(str(item["id"]))

        return {
            "proofs": tuple(proofs),
            "evidenceByItem": by_item,
            "passedItemIds": frozenset(passed_ids),
            "repairableItemIds": frozenset(repairable_ids),
            "summary": self._content_summary_from_locked_audit(
                items=items,
                proofs=proofs,
                repairable_item_ids=repairable_ids,
            ),
        }

    def _validate_locked_passed_evidence(
        self,
        *,
        evidence: Mapping[str, object],
        prior_evidence: Sequence[Mapping[str, object]],
    ) -> AcceptedPrimaryOneHostReceipt:
        item = evidence.get("item")
        if not isinstance(item, Mapping):
            raise ValueError("locked passed evidence is incomplete")
        attempt = int(item.get("attempt_count") or 0)
        current = self._locked_attempt_evidence(
            evidence=evidence,
            attempt=attempt,
        )
        candidate = current["candidate"]
        if attempt == 1:
            self._require_empty_locked_attempt_history(
                evidence=evidence,
                attempt=2,
            )
            attempt_one = None
        elif attempt == 2:
            if (
                recovery_dispatches(item=item, evidence=evidence) is not None
                or
                self._zero_call_number_sense_attempt_one_dispatches(
                    item=item,
                    evidence=evidence,
                )
                is not None
                or self._provider_rejected_addition_subtraction_attempt_one_dispatches(
                    item=item,
                    evidence=evidence,
                )
                is not None
            ):
                attempt_one = evidence
            else:
                attempt_one = self._locked_attempt_evidence(
                    evidence=evidence,
                    attempt=1,
                )
                self._validate_locked_rejected_history(
                    evidence=evidence,
                    item=item,
                    history_evidence=attempt_one,
                    prior_evidence=prior_evidence,
                )
        else:
            raise ValueError("locked passed attempt drift")
        expected_request_id = str(item.get("generation_request_id") or "") + (
            ".attempt2" if attempt == 2 else ""
        )
        if (
            str(item.get("status") or "") != "course_ready"
            or str(item.get("content_phase") or "") != "course_ready"
            or str(item.get("content_gate_status") or "") != "passed"
            or int(item.get("content_gate_passed_at") or 0) <= 0
            or attempt not in {1, 2}
            or int(item.get("content_claim_attempt_ordinal") or 0) != attempt
            or str(item.get("active_generation_request_id") or "")
            != expected_request_id
            or str(item.get("content_validation_contract_version") or "")
            != formal_content_validation_identity(preparation_authority_grade(item))["contentValidationContractVersion"]
            or not re.fullmatch(
                r"[0-9a-f]{64}",
                str(item.get("content_receipt_hash") or ""),
            )
            or item.get("content_lease_token") is not None
            or item.get("content_lease_expires_at") is not None
            or item.get("content_provider_attempt_hard_deadline_at") is not None
            or item.get("content_work_unit_deadline_at") is not None
            or str(item.get("course_id") or "")
            != str(candidate.get("course_id") or "")
            or str(item.get("course_version") or "")
            != str(candidate.get("course_version") or "")
        ):
            raise ValueError("locked passed item authority drift")
        plan = {
            "candidate": candidate,
            "dispatches": current["dispatches"],
            "historicalQuestionFingerprints": current[
                "historicalQuestionFingerprints"
            ],
            "priorEvidence": prior_evidence,
            "attemptOneEvidence": attempt_one,
        }
        host_evidence, target, identity, priors = self._content_host_evidence(
            plan=plan,
            item=item,
        )
        self._validate_locked_generation_persistence(
            evidence=current,
            item=item,
            candidate_course=host_evidence.candidate_course,
            expected_job_status="validated",
            expected_candidate_status="course_validated",
        )
        replay = self.primary_one_host_validator.validate_primary_one_host_gate(
            host_evidence,
            target=target,
            identity=identity,
            skill_boundary=self._content_boundary(item),
            accepted_host_receipts=priors,
        )
        proof = self._accepted_content_proofs(
            (
                {
                    **dict(evidence),
                    "candidate": current["candidate"],
                    "course": current["course"],
                },
            )
        )[0]
        self.primary_one_host_validator.validate_primary_one_accepted_receipt(
            proof
        )
        if (
            replay.outcome != "passed"
            or replay.course is None
            or replay.receipt != proof.receipt
            or replay.receipt_hash != proof.receipt_hash
            or self._canonical_content_json(replay.course)
            != self._canonical_content_json(proof.immutable_course)
        ):
            raise ValueError("locked passed Host replay drift")
        return proof

    @staticmethod
    def _locked_attempt_history(
        *,
        evidence: Mapping[str, object],
        attempt: int,
    ) -> Mapping[str, object]:
        histories = evidence.get("attemptHistories")
        if not isinstance(histories, Mapping):
            raise ValueError("locked attempt histories are missing")
        history = histories.get(attempt)
        if not isinstance(history, Mapping):
            raise ValueError("locked attempt history is missing")
        return history

    def _locked_attempt_evidence(
        self,
        *,
        evidence: Mapping[str, object],
        attempt: int,
    ) -> Mapping[str, object]:
        history = self._locked_attempt_history(
            evidence=evidence,
            attempt=attempt,
        )
        historical_by_attempt = evidence.get(
            "historicalQuestionFingerprintsByAttempt"
        )
        historical_fingerprints = (
            historical_by_attempt.get(attempt)
            if isinstance(historical_by_attempt, Mapping)
            else None
        )
        item = evidence.get("item")
        if not isinstance(item, Mapping):
            raise ValueError("locked attempt item is missing")
        expected_request_id = str(item.get("generation_request_id") or "") + (
            ".attempt2" if attempt == 2 else ""
        )
        dispatches = history.get("dispatches")
        jobs = history.get("jobs")
        candidates = history.get("candidates")
        courses = history.get("courses")
        if (
            str(history.get("requestId") or "") != expected_request_id
            or not isinstance(dispatches, Sequence)
            or not isinstance(jobs, Sequence)
            or not isinstance(candidates, Sequence)
            or not isinstance(courses, Sequence)
            or not isinstance(historical_fingerprints, Sequence)
            or len(jobs) != 1
            or len(candidates) != 1
            or len(courses) != 1
            or not isinstance(jobs[0], Mapping)
            or not isinstance(candidates[0], Mapping)
            or not isinstance(courses[0], Mapping)
        ):
            raise ValueError("locked attempt persistence cardinality drift")
        job = jobs[0]
        candidate = candidates[0]
        course = courses[0]
        if (
            str(job.get("request_id") or "") != expected_request_id
            or str(candidate.get("job_id") or "") != str(job.get("id") or "")
            or int(candidate.get("ordinal") or 0) != 1
            or str(course.get("id") or "")
            != str(candidate.get("course_id") or "")
            or str(course.get("version") or "")
            != str(candidate.get("course_version") or "")
        ):
            raise ValueError("locked attempt persistence identity drift")
        return {
            "dispatches": dispatches,
            "job": job,
            "candidate": candidate,
            "course": course,
            "historicalQuestionFingerprints": historical_fingerprints,
        }

    def _locked_host_pending_attempt_evidence(
        self,
        *,
        evidence: Mapping[str, object],
        attempt: int,
    ) -> Mapping[str, object]:
        history = self._locked_attempt_history(
            evidence=evidence,
            attempt=attempt,
        )
        historical_by_attempt = evidence.get(
            "historicalQuestionFingerprintsByAttempt"
        )
        historical_fingerprints = (
            historical_by_attempt.get(attempt)
            if isinstance(historical_by_attempt, Mapping)
            else None
        )
        item = evidence.get("item")
        if not isinstance(item, Mapping):
            raise ValueError("locked Host-pending item is missing")
        expected_request_id = str(item.get("generation_request_id") or "") + (
            ".attempt2" if attempt == 2 else ""
        )
        dispatches = history.get("dispatches")
        jobs = history.get("jobs")
        candidates = history.get("candidates")
        courses = history.get("courses")
        if (
            str(history.get("requestId") or "") != expected_request_id
            or not isinstance(dispatches, Sequence)
            or not isinstance(jobs, Sequence)
            or not isinstance(candidates, Sequence)
            or not isinstance(courses, Sequence)
            or not isinstance(historical_fingerprints, Sequence)
            or len(jobs) != 1
            or len(candidates) != 1
            or len(courses) not in {0, 1}
            or not isinstance(jobs[0], Mapping)
            or not isinstance(candidates[0], Mapping)
            or (courses and not isinstance(courses[0], Mapping))
        ):
            raise ValueError("locked Host-pending persistence cardinality drift")
        job = jobs[0]
        candidate = candidates[0]
        course = courses[0] if courses else None
        if (
            str(job.get("request_id") or "") != expected_request_id
            or str(candidate.get("job_id") or "") != str(job.get("id") or "")
            or int(candidate.get("ordinal") or 0) != 1
            or (
                course is not None
                and (
                    str(course.get("id") or "")
                    != str(candidate.get("course_id") or "")
                    or str(course.get("version") or "")
                    != str(candidate.get("course_version") or "")
                )
            )
        ):
            raise ValueError("locked Host-pending persistence identity drift")
        return {
            "dispatches": dispatches,
            "job": job,
            "candidate": candidate,
            "course": course,
            "historicalQuestionFingerprints": historical_fingerprints,
        }

    def _require_empty_locked_attempt_history(
        self,
        *,
        evidence: Mapping[str, object],
        attempt: int,
    ) -> None:
        history = self._locked_attempt_history(
            evidence=evidence,
            attempt=attempt,
        )
        for key in ("dispatches", "jobs", "candidates", "courses"):
            value = history.get(key)
            if not isinstance(value, Sequence) or value:
                raise ValueError("unexpected locked attempt residue")

    def _validate_locked_rejected_evidence(
        self,
        *,
        evidence: Mapping[str, object],
        prior_evidence: Sequence[Mapping[str, object]],
    ) -> None:
        item = evidence.get("item")
        if not isinstance(item, Mapping):
            raise ValueError("locked rejected evidence is incomplete")
        self._require_empty_locked_attempt_history(
            evidence=evidence,
            attempt=2,
        )
        attempt_one = self._locked_attempt_evidence(
            evidence=evidence,
            attempt=1,
        )
        candidate = attempt_one.get("candidate")
        if (
            not isinstance(candidate, Mapping)
            or str(item.get("status") or "") != "failed"
            or str(item.get("content_phase") or "") != "failed"
            or str(item.get("content_gate_status") or "")
            != "failed_deterministic"
            or int(item.get("attempt_count") or 0) != 1
            or int(item.get("content_claim_attempt_ordinal") or 0) != 1
            or str(item.get("active_generation_request_id") or "")
            != str(item.get("generation_request_id") or "")
            or str(item.get("course_id") or "")
            != str(candidate.get("course_id") or "")
            or str(item.get("course_version") or "")
            != str(candidate.get("course_version") or "")
            or item.get("content_lease_token") is not None
            or item.get("content_lease_expires_at") is not None
            or item.get("content_provider_attempt_hard_deadline_at") is not None
            or item.get("content_work_unit_deadline_at") is not None
        ):
            raise ValueError("locked rejected item authority drift")
        self._validate_locked_rejected_history(
            evidence=evidence,
            item=item,
            history_evidence=attempt_one,
            prior_evidence=prior_evidence,
        )

    def _validate_locked_rejected_history(
        self,
        *,
        evidence: Mapping[str, object],
        item: Mapping[str, object],
        history_evidence: Mapping[str, object],
        prior_evidence: Sequence[Mapping[str, object]],
    ) -> None:
        candidate = history_evidence.get("candidate")
        job = history_evidence.get("job")
        course = history_evidence.get("course")
        if not all(
            isinstance(value, Mapping)
            for value in (candidate, job, course)
        ):
            raise ValueError("locked rejected history is incomplete")
        raw_dispatches = history_evidence.get("dispatches")
        if not isinstance(raw_dispatches, Sequence) or not raw_dispatches:
            raise ValueError("locked rejected dispatch history is incomplete")
        historical_deadlines = {
            (
                row.get("attempt_started_at"),
                row.get("attempt_hard_deadline_at"),
            )
            for row in raw_dispatches
            if isinstance(row, Mapping)
            and type(row.get("attempt_started_at")) is int
            and type(row.get("attempt_hard_deadline_at")) is int
        }
        if len(historical_deadlines) != 1 or len(raw_dispatches) != sum(
            isinstance(row, Mapping)
            and type(row.get("attempt_started_at")) is int
            and type(row.get("attempt_hard_deadline_at")) is int
            for row in raw_dispatches
        ):
            raise ValueError("locked rejected dispatch deadline drift")
        historical_start, historical_hard_deadline = next(
            iter(historical_deadlines)
        )
        if (
            historical_start <= 0
            or not provider_attempt_deadline_is_valid(
                historical_start, historical_hard_deadline
            )
        ):
            raise ValueError("locked rejected dispatch deadline drift")
        attempt_item = {
            **dict(item),
            "status": "failed",
            "content_phase": "failed",
            "content_gate_status": "failed_deterministic",
            "attempt_count": 1,
            "content_claim_attempt_ordinal": 1,
            "active_generation_request_id": str(
                item.get("generation_request_id") or ""
            ),
            "course_id": candidate.get("course_id"),
            "course_version": candidate.get("course_version"),
            "content_lease_token": None,
            "content_lease_expires_at": None,
            "content_attempt_started_at": historical_start,
            "content_provider_attempt_hard_deadline_at": None,
            "content_work_unit_deadline_at": None,
        }
        plan = {
            "candidate": candidate,
            "dispatches": history_evidence.get("dispatches"),
            "historicalQuestionFingerprints": history_evidence.get(
                "historicalQuestionFingerprints"
            ),
            "priorEvidence": prior_evidence,
        }
        host_evidence, target, identity, priors = self._content_host_evidence(
            plan=plan, item=attempt_item
        )
        self._validate_locked_generation_persistence(
            evidence=history_evidence,
            item=attempt_item,
            candidate_course=host_evidence.candidate_course,
            expected_job_status="failed",
            expected_candidate_status="rejected",
        )
        replay = self.primary_one_host_validator.validate_primary_one_host_gate(
            host_evidence,
            target=target,
            identity=identity,
            skill_boundary=self._content_boundary(item),
            accepted_host_receipts=priors,
        )
        envelope = self._decode_content_json(candidate.get("validation_json"))
        if (
            replay.outcome != "rejected"
            or replay.course is not None
            or replay.receipt != envelope.get("hostGateReceipt")
            or replay.receipt_hash != envelope.get("hostGateReceiptHash")
            or self._canonical_content_json(envelope)
            != self._canonical_content_json(
                {
                    "schemaVersion": formal_content_validation_identity(target.grade_code)["hostGateEvidenceSchemaVersion"],
                    "contentFingerprint": str(
                        replay.receipt.get("hostContentFingerprint") or ""
                    ),
                    "hostGateReceipt": replay.receipt,
                    "hostGateReceiptHash": replay.receipt_hash,
                }
            )
            or str(job.get("status") or "") != "failed"
            or str(job.get("request_id") or "")
            != str(attempt_item.get("generation_request_id") or "")
            or str(job.get("grade_code") or "")
            != str(attempt_item.get("grade_code") or "")
            or str(job.get("subject") or "")
            != str(attempt_item.get("subject") or "")
            or str(job.get("node_code") or "")
            != str(attempt_item.get("skill_id") or "")
            or str(job.get("curriculum_version") or "")
            != str(attempt_item.get("curriculum_version") or "")
            or str(job.get("boundary_version") or "")
            != str(attempt_item.get("boundary_version") or "")
            or str(job.get("generator") or "")
            != "openmaic_question_phase_v2"
            or int(job.get("requested_candidate_count") or 0) != 1
            or str(candidate.get("status") or "") != "rejected"
            or str(candidate.get("job_id") or "")
            != str(job.get("id") or "")
            or int(candidate.get("ordinal") or 0) != 1
            or candidate.get("published_at") is not None
            or str(attempt_item.get("status") or "") != "failed"
            or str(attempt_item.get("content_phase") or "") != "failed"
            or str(attempt_item.get("content_gate_status") or "")
            != "failed_deterministic"
            or int(attempt_item.get("attempt_count") or 0) != 1
            or int(attempt_item.get("content_claim_attempt_ordinal") or 0) != 1
            or str(attempt_item.get("active_generation_request_id") or "")
            != str(attempt_item.get("generation_request_id") or "")
            or attempt_item.get("content_lease_token") is not None
            or attempt_item.get("content_lease_expires_at") is not None
            or attempt_item.get("content_provider_attempt_hard_deadline_at") is not None
            or attempt_item.get("content_work_unit_deadline_at") is not None
            or str(attempt_item.get("course_id") or "")
            != str(candidate.get("course_id") or "")
            or str(attempt_item.get("course_version") or "")
            != str(candidate.get("course_version") or "")
            or str(candidate.get("course_id") or "")
            != str(course.get("id") or "")
            or str(candidate.get("course_version") or "")
            != str(course.get("version") or "")
        ):
            raise ValueError("locked rejected Host replay drift")

    def _validate_locked_generation_persistence(
        self,
        *,
        evidence: Mapping[str, object],
        item: Mapping[str, object],
        candidate_course: Mapping[str, object],
        expected_job_status: str,
        expected_candidate_status: str,
    ) -> None:
        job, candidate, expected_content_hash = (
            self._validate_locked_generation_envelope(
                evidence=evidence,
                item=item,
                candidate_course=candidate_course,
            )
        )
        course = evidence.get("course")
        if not isinstance(course, Mapping):
            raise ValueError("locked generation persistence is incomplete")
        request_id = str(item.get("active_generation_request_id") or "")
        rejected = (
            expected_job_status == "failed"
            and expected_candidate_status == "rejected"
        )
        passed = (
            expected_job_status == "validated"
            and expected_candidate_status == "course_validated"
        )
        envelope = self._decode_content_json(candidate.get("validation_json"))
        expected_safe_code = "preparation_content_validation_failed"
        error_state_exact = (
            (
                str(job.get("error_code") or "") == expected_safe_code
                and str(job.get("error_message_safe") or "")
                == "内容未通过本地确定性门禁。"
                and str(candidate.get("error_code") or "")
                == expected_safe_code
                and str(candidate.get("error_message_safe") or "")
                == "内容未通过本地确定性门禁。"
            )
            if rejected
            else (
                job.get("error_code") is None
                and job.get("error_message_safe") is None
                and candidate.get("error_code") is None
                and candidate.get("error_message_safe") is None
            )
        )
        course_state_exact = (
            str(course.get("grade_code") or "")
            == str(candidate_course["gradeCode"])
            and str(course.get("subject") or "")
            == str(candidate_course["subject"])
            and str(course.get("node_code") or "")
            == str(candidate_course["nodeCode"])
            and str(course.get("curriculum_version") or "")
            == str(item.get("curriculum_version") or "")
            and str(course.get("boundary_version") or "")
            == str(item.get("boundary_version") or "")
            and str(course.get("title") or "") == str(candidate_course["title"])
            and str(course.get("objective") or "")
            == str(candidate_course["objective"])
            and str(course.get("content_origin") or "")
            == "openmaic_generated"
            and (
                (
                    str(course.get("status") or "") == "unverified"
                    and str(course.get("quality_status") or "")
                    == "legacy_unreviewed"
                    and str(course.get("generation_content_hash") or "")
                    == expected_content_hash
                    and str(course.get("content_json") or "")
                    == self._canonical_content_json(candidate_course["content"])
                )
                if rejected
                else (
                    passed
                    and (
                        (
                            str(course.get("status") or "") == "validated"
                            and str(course.get("quality_status") or "")
                            == "auto_validated"
                            and course.get("published_at") is None
                        )
                        or (
                            str(course.get("status") or "") == "published"
                            and str(course.get("quality_status") or "")
                            == "released"
                            and course.get("published_at") is not None
                        )
                    )
                    and str(course.get("generation_content_hash") or "")
                    == str(envelope.get("contentFingerprint") or "")
                )
            )
        )
        if (
            not (rejected or passed)
            or not error_state_exact
            or not course_state_exact
            or str(job.get("status") or "") != expected_job_status
            or str(candidate.get("status") or "")
            != expected_candidate_status
            or str(course.get("id") or "") != str(candidate_course["id"])
            or str(course.get("version") or "")
            != str(candidate_course["version"])
            or str(course.get("generation_request_id") or "") != request_id
            or str(course.get("generator") or "")
            != "openmaic_question_phase_v2"
            or (
                rejected
                and course.get("published_at") is not None
            )
            or course.get("retired_at") is not None
        ):
            raise ValueError("locked generation persistence drift")

    def _validate_locked_generation_envelope(
        self,
        *,
        evidence: Mapping[str, object],
        item: Mapping[str, object],
        candidate_course: Mapping[str, object],
    ) -> tuple[Mapping[str, object], Mapping[str, object], str]:
        job = evidence.get("job")
        candidate = evidence.get("candidate")
        if not isinstance(job, Mapping) or not isinstance(candidate, Mapping):
            raise ValueError("locked generation persistence is incomplete")
        request_id = str(item.get("active_generation_request_id") or "")
        generator_profile = self._content_profile_payload("generator")
        expected_job_id = "learning_course_job_" + hashlib.sha256(
            request_id.encode("utf-8")
        ).hexdigest()[:32]
        expected_request_fingerprint = hashlib.sha256(
            self._canonical_content_json(
                {
                    "gradeCode": item["grade_code"],
                    "subject": item["subject"],
                    "nodeCode": item["skill_id"],
                    "curriculumVersion": item["curriculum_version"],
                    "boundaryVersion": item["boundary_version"],
                    "generator": "openmaic_question_phase_v2",
                    "providerProfile": generator_profile,
                    "requestedCandidateCount": 1,
                }
            ).encode("utf-8")
        ).hexdigest()
        expected_candidate_id = "learning_course_candidate_" + hashlib.sha256(
            f"{expected_job_id}:1".encode("utf-8")
        ).hexdigest()[:32]
        expected_content_hash = hashlib.sha256(
            self._canonical_content_json(
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
        if (
            not request_id
            or str(job.get("id") or "") != expected_job_id
            or str(job.get("request_id") or "") != request_id
            or str(job.get("request_fingerprint") or "")
            != expected_request_fingerprint
            or str(job.get("grade_code") or "")
            != str(item.get("grade_code") or "")
            or str(job.get("subject") or "")
            != str(item.get("subject") or "")
            or str(job.get("node_code") or "")
            != str(item.get("skill_id") or "")
            or str(job.get("curriculum_version") or "")
            != str(item.get("curriculum_version") or "")
            or str(job.get("boundary_version") or "")
            != str(item.get("boundary_version") or "")
            or str(job.get("generator") or "")
            != "openmaic_question_phase_v2"
            or str(job.get("provider") or "")
            != str(generator_profile["name"])
            or str(job.get("model") or "")
            != str(generator_profile["model"])
            or str(job.get("prompt_version") or "")
            != QUESTION_CONTRACT_VERSION
            or int(job.get("requested_candidate_count") or 0) != 1
            or str(candidate.get("id") or "") != expected_candidate_id
            or str(candidate.get("job_id") or "") != expected_job_id
            or int(candidate.get("ordinal") or 0) != 1
            or str(candidate.get("course_id") or "")
            != str(candidate_course["id"])
            or str(candidate.get("course_version") or "")
            != str(candidate_course["version"])
            or str(candidate.get("grade_code") or "")
            != str(candidate_course["gradeCode"])
            or str(candidate.get("subject") or "")
            != str(candidate_course["subject"])
            or str(candidate.get("node_code") or "")
            != str(candidate_course["nodeCode"])
            or str(candidate.get("curriculum_version") or "")
            != str(item.get("curriculum_version") or "")
            or str(candidate.get("boundary_version") or "")
            != str(item.get("boundary_version") or "")
            or str(candidate.get("title") or "")
            != str(candidate_course["title"])
            or str(candidate.get("objective") or "")
            != str(candidate_course["objective"])
            or str(candidate.get("content_hash") or "")
            != expected_content_hash
            or str(candidate.get("content_json") or "")
            != self._canonical_content_json(candidate_course["content"])
            or candidate.get("published_at") is not None
        ):
            raise ValueError("locked generation persistence drift")
        return job, candidate, expected_content_hash

    def _validate_locked_host_pending_persistence(
        self,
        *,
        evidence: Mapping[str, object],
        item: Mapping[str, object],
        candidate_course: Mapping[str, object],
        attempt_one_evidence: Mapping[str, object] | None,
    ) -> None:
        job, candidate, _content_hash = self._validate_locked_generation_envelope(
            evidence=evidence,
            item=item,
            candidate_course=candidate_course,
        )
        if (
            str(job.get("status") or "") != "generating"
            or job.get("error_code") is not None
            or job.get("error_message_safe") is not None
            or job.get("completed_at") is not None
            or str(candidate.get("status") or "") != "generated"
            or candidate.get("validation_json") is not None
            or candidate.get("error_code") is not None
            or candidate.get("error_message_safe") is not None
            or candidate.get("published_at") is not None
            or str(item.get("course_id") or "")
            != str(candidate.get("course_id") or "")
            or str(item.get("course_version") or "")
            != str(candidate.get("course_version") or "")
        ):
            raise ValueError("Host retry graph persistence drift")
        course = evidence.get("course")
        if attempt_one_evidence is None:
            if course is not None:
                raise ValueError("Host retry graph course residue")
            return
        attempt_one_course = attempt_one_evidence.get("course")
        if course is None:
            return
        if (
            not isinstance(course, Mapping)
            or not isinstance(attempt_one_course, Mapping)
            or dict(course) != dict(attempt_one_course)
        ):
            raise ValueError("Host retry graph prior course drift")

    def _content_summary_from_locked_audit(
        self,
        *,
        items: Sequence[Mapping[str, object]],
        proofs: Sequence[AcceptedPrimaryOneHostReceipt],
        repairable_item_ids: set[str],
    ) -> Mapping[str, object]:
        passed_targets = [proof.target for proof in proofs]
        if not items:
            raise ValueError("content summary requires immutable grade inventory")
        target = canonical_preparation_target_for(items[0])
        if any(preparation_authority_grade(item) != target["gradeCode"] for item in items):
            raise ValueError("content summary mixes grades")
        failed = [
            item
            for item in items
            if str(item.get("status") or "") == "failed"
            and str(item.get("id") or "") not in repairable_item_ids
        ]
        target_counts = {subject: values["totalCourseCount"] for subject, values in target["subjectTargets"].items()}
        canary_keys = {
            (row["subject"], row["skillId"], row["variantOrdinal"])
            for row in target["canaryManifest"]["targets"]
        }
        passed_canaries = sum(
            1
            for target in passed_targets
            if (target.subject, target.skill_id, target.variant_ordinal)
            in canary_keys
        )
        failed_canaries = sum(
            1
            for item in failed
            if (
                str(item.get("subject") or ""),
                str(item.get("skill_id") or ""),
                int(item.get("variant_ordinal") or 0),
            )
            in canary_keys
        )
        return {
            "contentCandidateItemCount": len(passed_targets),
            "contentFailedItemCount": len(failed),
            "subjectContentProgress": {
                subject: {
                    "candidateCount": sum(
                        1 for target in passed_targets if target.subject == subject
                    ),
                    "failedCount": sum(
                        1
                        for item in failed
                        if str(item.get("subject") or "") == subject
                    ),
                    "targetCount": target_count,
                }
                for subject, target_count in target_counts.items()
            },
            "canary": {
                "targetCount": 3,
                "candidateCount": passed_canaries,
                "failedCount": failed_canaries,
                "passed": passed_canaries == 3,
            },
            "canActivate": False,
        }

    def _authorize_content_attempt_two(
        self,
        *,
        build_id: str,
        plan: Mapping[str, object],
        item: Mapping[str, object],
        summary: Mapping[str, object],
        conn: object | None = None,
    ) -> ContentAdvanceResult:
        def fail_locked_or_terminal() -> ContentAdvanceResult:
            if conn is not None:
                self.repository.fence_content_failure(
                    conn,
                    build_id=build_id,
                    item_id=str(item["id"]),
                    error_code="preparation_content_contract_drift",
                    now=self._trusted_content_now(),
                )
                return ContentAdvanceResult(
                    "failed", build_id, str(item["id"]), summary
                )
            return self._content_contract_failure(build_id, item, summary)

        attempt_one = plan.get("attemptOneEvidence")
        if not isinstance(attempt_one, Mapping):
            return fail_locked_or_terminal()
        candidate = attempt_one.get("candidate")
        if not isinstance(candidate, Mapping) and "attemptHistories" in attempt_one:
            try:
                attempt_one = self._locked_attempt_evidence(
                    evidence=attempt_one,
                    attempt=1,
                )
                candidate = attempt_one.get("candidate")
            except (KeyError, TypeError, ValueError):
                return fail_locked_or_terminal()
        if not isinstance(candidate, Mapping):
            return fail_locked_or_terminal()
        replay_plan = {
            **dict(plan),
            "candidate": candidate,
            "dispatches": attempt_one.get("dispatches"),
        }
        try:
            evidence, target, identity, prior = self._content_host_evidence(
                plan=replay_plan, item=item
            )
            rerun = self.primary_one_host_validator.validate_primary_one_host_gate(
                evidence,
                target=target,
                identity=identity,
                skill_boundary=self._content_boundary(item),
                accepted_host_receipts=prior,
            )
            envelope = self._decode_content_json(candidate.get("validation_json"))
            stored_receipt = envelope.get("hostGateReceipt")
            stored_hash = envelope.get("hostGateReceiptHash")
            if (
                rerun.outcome != "rejected"
                or rerun.course is not None
                or rerun.receipt != stored_receipt
                or rerun.receipt_hash != stored_hash
                or self._canonical_content_json(envelope)
                != self._canonical_content_json(
                    {
                        "schemaVersion": formal_content_validation_identity(target.grade_code)["hostGateEvidenceSchemaVersion"],
                        "contentFingerprint": str(
                            rerun.receipt.get("hostContentFingerprint") or ""
                        ),
                        "hostGateReceipt": rerun.receipt,
                        "hostGateReceiptHash": rerun.receipt_hash,
                    }
                )
            ):
                raise PrimaryOneHostGateControlError(
                    "attempt-one rejection replay drift"
                )
        except (
            PrimaryOneHostGateControlError,
            PrimaryOneHostGateDependencyError,
            KeyError,
            TypeError,
            ValueError,
        ):
            return fail_locked_or_terminal()
        if conn is not None:
            claimed = self.repository._claim_content_attempt_two_locked(
                conn,
                build_id=build_id,
                item_id=str(item["id"]),
                attempt_one_request_id=str(item["generation_request_id"]),
                attempt_one_course_id=str(item["course_id"]),
                attempt_one_course_version=str(item["course_version"]),
                now=self._trusted_content_now(),
            )
        else:
            with self.repository.transaction() as transaction_conn:
                claimed = self.repository._claim_content_attempt_two_locked(
                    transaction_conn,
                    build_id=build_id,
                    item_id=str(item["id"]),
                    attempt_one_request_id=str(item["generation_request_id"]),
                    attempt_one_course_id=str(item["course_id"]),
                    attempt_one_course_version=str(item["course_version"]),
                    now=self._trusted_content_now(),
                )
        # The locked authorization path already holds release/build/all-item
        # proof locks.  Re-opening a summary transaction here would wait on
        # our own item locks; the pre-claim audit summary remains exact because
        # an attempt-2 claim does not create a passed or failed proof.
        refreshed_summary = (
            summary
            if conn is not None
            else self._content_summary_after_transition(build_id)
        )
        return ContentAdvanceResult(
            "progressed" if claimed is not None else "stale",
            build_id,
            str(item["id"]),
            refreshed_summary,
        )

    def _advance_content_provider(
        self,
        *,
        build_id: str,
        plan: Mapping[str, object],
        item: Mapping[str, object],
        summary: Mapping[str, object],
        heartbeat: Callable[[], bool],
    ) -> ContentAdvanceResult:
        dispatches = plan.get("dispatches")
        if not isinstance(dispatches, Sequence):
            return self._content_contract_failure(build_id, item, summary)
        try:
            command, initial_checkpoint = self._content_phase_command(
                item=item, dispatches=dispatches, plan=plan
            )
        except (KeyError, TypeError, ValueError):
            return self._content_contract_failure(build_id, item, summary)
        from services.learning_formal_question_preflight import (
            FormalQuestionPreflightError, validate_formal_phase_question_checkpoint,
        )
        try:
            validate_formal_phase_question_checkpoint(command)
        except FormalQuestionPreflightError as exc:
            logging.getLogger("mira.staged_content").warning(
                "formal objective preflight rejected grade=%s phase=%s difficulty=%s detail=%s",
                command.grade_code, command.phase, command.difficulty_code, str(exc),
            )
            return self._content_terminal_failure(
                build_id, item, summary, error_code="preparation_content_validation_failed",
            )
        work = ContentPhaseWork(
            command=command,
            attempt_initial_checkpoint=initial_checkpoint,
            item_lease_token=str(item["content_lease_token"]),
            attempt_started_at=int(item["content_attempt_started_at"]),
            attempt_hard_deadline_at=int(
                item["content_provider_attempt_hard_deadline_at"]
            ),
            work_unit_deadline_at=int(item["content_work_unit_deadline_at"]),
            lease_expires_at=int(item["content_lease_expires_at"]),
        )
        try:
            advance = self.staged_content_candidate_generator.advance(
                work, heartbeat=heartbeat
            )
        except Exception:
            return self._content_terminal_failure(
                build_id,
                item,
                summary,
                error_code="preparation_content_provider_unavailable",
            )
        kind = str(getattr(advance, "kind", "dependency_retry"))
        process_started = bool(getattr(advance, "process_started", False))
        if kind == "busy":
            return ContentAdvanceResult(
                "busy", build_id, str(item["id"]), summary
            )
        if kind == "dependency_retry":
            if process_started:
                return self._content_contract_failure(build_id, item, summary)
            now = self._trusted_content_now()
            with self.repository.transaction() as conn:
                released = self.repository.release_content_provider_dependency(
                    conn,
                    item_id=str(item["id"]),
                    lease_token=str(item["content_lease_token"]),
                    now=now,
                )
            if not released:
                return self._content_contract_failure(build_id, item, summary)
            return ContentAdvanceResult(
                "dependency_retry", build_id, str(item["id"]), summary
            )
        if kind in {"ambiguous", "failed_safe"}:
            safe_error_code = str(
                getattr(getattr(advance, "result", None), "safe_error_code", "")
                or ""
            )
            if kind == "ambiguous":
                code = "preparation_provider_dispatch_outcome_unknown"
            elif safe_error_code in _QUESTION_CONTENT_VALIDATION_FAILURE_CODES:
                code = "preparation_content_validation_failed"
            else:
                code = "preparation_content_provider_unavailable"
            return self._content_terminal_failure(
                build_id, item, summary, error_code=code
            )
        if kind == "stale":
            with self.repository.transaction() as conn:
                reconciliation = self.repository.reconcile_content_provider_stale(
                    conn,
                    build_id=build_id,
                    item_id=str(item["id"]),
                    logical_attempt=int(item["attempt_count"]),
                    generation_request_id=str(item["active_generation_request_id"]),
                    phase=command.phase,
                    phase_ordinal=command.phase_ordinal,
                    lease_token=str(item["content_lease_token"]),
                    now=self._trusted_content_now(),
                )
            if isinstance(reconciliation, Mapping):
                reconciled_action = str(reconciliation.get("action") or "stale")
            else:
                reconciled_action = str(reconciliation or "stale")
            if reconciled_action != "succeeded":
                refreshed = self._content_summary_after_transition(
                    build_id,
                    terminal_already_fenced=(
                        reconciled_action == "failed"
                    ),
                )
                return ContentAdvanceResult(
                    "failed" if reconciled_action == "failed" else (
                        "busy" if reconciled_action == "busy" else "stale"
                    ),
                    build_id,
                    str(item["id"]),
                    refreshed,
                )
            if not isinstance(reconciliation, Mapping):
                return self._content_contract_failure(build_id, item, summary)
            reconciled_item = reconciliation.get("item")
            reconciled_dispatches = reconciliation.get("dispatches")
            reconciled_dispatch = reconciliation.get("dispatch")
            if (
                not isinstance(reconciled_item, Mapping)
                or not isinstance(reconciled_dispatches, Sequence)
                or not isinstance(reconciled_dispatch, Mapping)
            ):
                return self._content_contract_failure(build_id, item, summary)
            item = reconciled_item
            dispatches = reconciled_dispatches
            replay_plan = {**dict(plan), "dispatches": dispatches}
            try:
                command, initial_checkpoint = self._content_phase_command(
                    item=item,
                    dispatches=dispatches,
                    plan=replay_plan,
                )
                checkpoint = self._decode_content_json(
                    reconciled_dispatch.get("checkpoint_json")
                )
                if hashlib.sha256(
                    self._canonical_content_json(checkpoint).encode("utf-8")
                ).hexdigest() != str(
                    reconciled_dispatch.get("output_sha256") or ""
                ):
                    raise ValueError("reconciled provider output hash drift")
            except (KeyError, TypeError, ValueError):
                return self._content_contract_failure(build_id, item, summary)
        else:
            result = getattr(advance, "result", None)
            checkpoint = getattr(result, "checkpoint", None)
            if (
                kind != "succeeded"
                or result is None
                or not isinstance(checkpoint, Mapping)
                or str(getattr(result, "phase", "")) != command.phase
                or int(getattr(result, "phase_ordinal", 0)) != command.phase_ordinal
            ):
                return self._content_contract_failure(build_id, item, summary)
        now = self._trusted_content_now()
        contract_failed = False
        persisted = None
        with self.repository.transaction() as conn:
            try:
                authority = self.repository.load_content_provider_finalize_authority(
                    conn,
                    build_id=build_id,
                    item_id=str(item["id"]),
                    logical_attempt=int(item["attempt_count"]),
                    generation_request_id=str(item["active_generation_request_id"]),
                    phase=command.phase,
                    phase_ordinal=command.phase_ordinal,
                    lease_token=str(item["content_lease_token"]),
                    attempt_started_at=int(item["content_attempt_started_at"]),
                    outer_deadline_at=int(
                        item["content_provider_attempt_hard_deadline_at"]
                    ),
                    work_deadline_at=int(item["content_work_unit_deadline_at"]),
                    now=now,
                )
                release = authority.get("release")
                build = authority.get("build")
                locked_items = authority.get("items")
                locked_item = authority.get("item")
                locked_dispatches = authority.get("dispatches")
                persisted_dispatch = authority.get("persistedDispatch")
                if (
                    not isinstance(release, Mapping)
                    or not isinstance(build, Mapping)
                    or not isinstance(locked_items, Sequence)
                    or not isinstance(locked_item, Mapping)
                    or not isinstance(locked_dispatches, Sequence)
                    or not isinstance(persisted_dispatch, Mapping)
                    or not self.repository._content_authority_is_exact(
                        conn,
                        release=release,
                        build=build,
                        rows=locked_items,
                    )
                    or not self.repository._provider_cas_matches(
                        locked_item,
                        logical_attempt=int(item["attempt_count"]),
                        generation_request_id=str(
                            item["active_generation_request_id"]
                        ),
                        phase=command.phase,
                        phase_ordinal=command.phase_ordinal,
                        lease_token=str(item["content_lease_token"]),
                        attempt_started_at=int(item["content_attempt_started_at"]),
                        outer_deadline_at=int(
                            item["content_provider_attempt_hard_deadline_at"]
                        ),
                        work_deadline_at=int(
                            item["content_work_unit_deadline_at"]
                        ),
                        now=now,
                    )
                    or str(persisted_dispatch.get("status") or "")
                    != "succeeded"
                ):
                    raise ValueError("locked Provider finalize authority drift")
                locked_plan = {
                    "historicalQuestionFingerprints": authority.get(
                        "historicalQuestionFingerprints"
                    ),
                    "priorEvidence": authority.get("priorEvidence"),
                    "attemptOneEvidence": authority.get("attemptOneEvidence"),
                }
                locked_command, _ = self._content_phase_command(
                    item=locked_item,
                    dispatches=locked_dispatches,
                    plan=locked_plan,
                )
                if locked_command != command:
                    raise ValueError("locked Provider command drift")
                persisted_checkpoint = self._decode_content_json(
                    persisted_dispatch.get("checkpoint_json")
                )
                if (
                    hashlib.sha256(
                        self._canonical_content_json(
                            persisted_checkpoint
                        ).encode("utf-8")
                    ).hexdigest()
                    != str(persisted_dispatch.get("output_sha256") or "")
                    or self._canonical_content_json(persisted_checkpoint)
                    != self._canonical_content_json(checkpoint)
                ):
                    raise ValueError("locked Provider output drift")
                execution = question_phase_execution_authority(
                    locked_command.phase,
                    locked_command.phase_ordinal,
                )
                locked_prepared = self._content_provider_preflight(
                    locked_command
                )
                if (
                    locked_prepared.input_sha256
                    != str(persisted_dispatch.get("input_sha256") or "")
                    or locked_prepared.profile_sha256
                    != str(persisted_dispatch.get("profile") or "")
                ):
                    raise ValueError("locked Provider input drift")
                succeeded = self._succeeded_content_checkpoints(
                    locked_dispatches
                )
                next_phase = self._next_content_phase(
                    locked_command.phase,
                    locked_command.phase_ordinal,
                    persisted_checkpoint,
                    succeeded=succeeded,
                )
                final_candidate_key = execution["finalCandidateKey"]
                if next_phase is None and not isinstance(
                    final_candidate_key, str
                ):
                    raise ValueError("terminal phase cannot supply a candidate")
                candidate = (
                    persisted_checkpoint.get(final_candidate_key)
                    if next_phase is None
                    else None
                )
                persisted = self.repository._complete_content_provider_phase_locked(
                    conn,
                    locked_item=locked_item,
                    locked_build=build,
                    locked_items=locked_items,
                    persisted_dispatch_id=str(persisted_dispatch["id"]),
                    expected_next_phase=(
                        next_phase[0] if next_phase is not None else None
                    ),
                    expected_next_phase_ordinal=(
                        next_phase[1] if next_phase is not None else None
                    ),
                    candidate_course=(
                        candidate if isinstance(candidate, Mapping) else None
                    ),
                    generator_profile=self._content_profile_payload("generator"),
                    now=now,
                )
            except (KeyError, TypeError, ValueError):
                contract_failed = True
                self.repository.fence_content_failure(
                    conn,
                    build_id=build_id,
                    item_id=str(item["id"]),
                    error_code="preparation_content_contract_drift",
                    now=now,
                )
        contract_failed, refreshed_summary = self._content_finalize_outcome(
            build_id=build_id,
            persisted=persisted,
            explicit_failed=contract_failed,
        )
        return ContentAdvanceResult(
            (
                "failed"
                if contract_failed
                else ("progressed" if persisted is not None else "stale")
            ),
            build_id,
            str(item["id"]),
            refreshed_summary,
        )

    def _advance_content_host(
        self,
        *,
        build_id: str,
        plan: Mapping[str, object],
        item: Mapping[str, object],
        summary: Mapping[str, object],
    ) -> ContentAdvanceResult:
        try:
            evidence, target, identity, prior = self._content_host_evidence(
                plan=plan, item=item
            )
            result = self.primary_one_host_validator.validate_primary_one_host_gate(
                evidence,
                target=target,
                identity=identity,
                skill_boundary=self._content_boundary(item),
                accepted_host_receipts=prior,
            )
            if result.outcome == "passed" and target.variant_ordinal == 3:
                variants = [
                    PrimaryOneValidatedVariant(
                        target=proof.target,
                        immutable_course=proof.immutable_course,
                        receipt=proof.receipt,
                        receipt_hash=proof.receipt_hash,
                    )
                    for proof in prior
                ]
                if result.course is None:
                    raise PrimaryOneHostGateControlError(
                        "passed Host result omitted course"
                    )
                variants.append(
                    PrimaryOneValidatedVariant(
                        target=target,
                        immutable_course=result.course,
                        receipt=result.receipt,
                        receipt_hash=result.receipt_hash,
                    )
                )
                self.catalog_validator.validate_primary_one_variant_set(variants)
        except PrimaryOneHostGateDependencyError:
            now = self._trusted_content_now()
            with self.repository.transaction() as conn:
                released = self.repository.release_content_host_dependency(
                    conn,
                    build_id=build_id,
                    item_id=str(item["id"]),
                    logical_attempt=int(item["attempt_count"]),
                    generation_request_id=str(
                        item["active_generation_request_id"]
                    ),
                    gate_ordinal=int(item["content_gate_attempt_count"]),
                    lease_token=str(item["content_lease_token"]),
                    work_deadline_at=int(
                        item["content_work_unit_deadline_at"]
                    ),
                    now=now,
                )
            refreshed_summary = (
                self._content_summary_after_transition(
                    build_id,
                    terminal_already_fenced=True,
                )
                if released == "failed"
                else summary
            )
            return ContentAdvanceResult(
                (
                    released
                    if released in {"dependency_retry", "failed", "stale"}
                    else "dependency_retry" if released else "stale"
                ),
                build_id,
                str(item["id"]),
                refreshed_summary,
            )
        except (PrimaryOneHostGateControlError, KeyError, TypeError, ValueError):
            return self._content_contract_failure(build_id, item, summary)
        except Exception:
            return self._content_contract_failure(build_id, item, summary)
        now = self._trusted_content_now()
        finalize_failed = False
        with self.repository.transaction() as conn:
            try:
                if hasattr(
                    self.repository, "load_content_host_finalize_authority"
                ):
                    locked_plan = (
                        self.repository.load_content_host_finalize_authority(
                            conn,
                            build_id=build_id,
                            item_id=str(item["id"]),
                            logical_attempt=int(item["attempt_count"]),
                            generation_request_id=str(
                                item["active_generation_request_id"]
                            ),
                            gate_ordinal=int(
                                item["content_gate_attempt_count"]
                            ),
                            lease_token=str(item["content_lease_token"]),
                            work_deadline_at=int(
                                item["content_work_unit_deadline_at"]
                            ),
                            now=now,
                        )
                    )
                    locked_item = locked_plan.get("item")
                    if not isinstance(locked_item, Mapping):
                        raise ValueError("locked Host item is missing")
                    (
                        locked_evidence,
                        locked_target,
                        locked_identity,
                        locked_prior,
                    ) = self._content_host_evidence(
                        plan=locked_plan,
                        item=locked_item,
                    )
                    locked_result = self.primary_one_host_validator.validate_primary_one_host_gate(
                        locked_evidence,
                        target=locked_target,
                        identity=locked_identity,
                        skill_boundary=self._content_boundary(locked_item),
                        accepted_host_receipts=locked_prior,
                    )
                    if (
                        locked_evidence != evidence
                        or locked_target != target
                        or locked_identity != identity
                        or locked_prior != prior
                        or locked_result.outcome != result.outcome
                        or locked_result.course != result.course
                        or locked_result.receipt != result.receipt
                        or locked_result.receipt_hash != result.receipt_hash
                    ):
                        raise ValueError("Host finalize evidence changed")
                    if (
                        locked_result.outcome == "passed"
                        and locked_target.variant_ordinal == 3
                    ):
                        if locked_result.course is None:
                            raise ValueError("locked Host course is missing")
                        self.catalog_validator.validate_primary_one_variant_set(
                            [
                                *(
                                    PrimaryOneValidatedVariant(
                                        target=proof.target,
                                        immutable_course=proof.immutable_course,
                                        receipt=proof.receipt,
                                        receipt_hash=proof.receipt_hash,
                                    )
                                    for proof in locked_prior
                                ),
                                PrimaryOneValidatedVariant(
                                    target=locked_target,
                                    immutable_course=locked_result.course,
                                    receipt=locked_result.receipt,
                                    receipt_hash=locked_result.receipt_hash,
                                ),
                            ]
                        )
                persisted = self.repository.complete_content_host_gate(
                    conn,
                    build_id=build_id,
                    item_id=str(item["id"]),
                    logical_attempt=int(item["attempt_count"]),
                    generation_request_id=str(
                        item["active_generation_request_id"]
                    ),
                    course=result.course,
                    receipt=result.receipt,
                    receipt_hash=result.receipt_hash,
                    outcome=result.outcome,
                    lease_token=str(item["content_lease_token"]),
                    gate_ordinal=int(item["content_gate_attempt_count"]),
                    now=now,
                )
            except (
                PrimaryOneHostGateControlError,
                PrimaryOneHostGateDependencyError,
                KeyError,
                TypeError,
                ValueError,
            ):
                self.repository.fence_content_failure(
                    conn,
                    build_id=build_id,
                    item_id=str(item["id"]),
                    error_code="preparation_content_contract_drift",
                    now=now,
                )
                persisted = None
                finalize_failed = True
        finalize_failed, refreshed_summary = self._content_finalize_outcome(
            build_id=build_id,
            persisted=persisted,
            explicit_failed=finalize_failed,
        )
        return ContentAdvanceResult(
            (
                "failed"
                if finalize_failed
                else "progressed" if persisted is not None else "stale"
            ),
            build_id,
            str(item["id"]),
            refreshed_summary,
        )

    @staticmethod
    def _empty_content_summary() -> dict[str, object]:
        return {
            "contentCandidateItemCount": 0,
            "contentFailedItemCount": 0,
            "subjectContentProgress": {
                "chinese": {
                    "candidateCount": 0,
                    "failedCount": 0,
                    "targetCount": 12,
                },
                "math": {
                    "candidateCount": 0,
                    "failedCount": 0,
                    "targetCount": 9,
                },
                "english": {
                    "candidateCount": 0,
                    "failedCount": 0,
                    "targetCount": 9,
                },
            },
            "canary": {
                "targetCount": 3,
                "candidateCount": 0,
                "failedCount": 0,
                "passed": False,
            },
            "canActivate": False,
        }

    def _trusted_content_now(self) -> int:
        value = self._content_clock_ms()
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("trusted content clock is invalid")
        return value

    def _content_provider_preflight(
        self,
        command: QuestionPhaseCommand,
    ) -> object:
        canonicalize = getattr(
            self.staged_content_candidate_generator,
            "canonicalize_phase",
            None,
        )
        if not callable(canonicalize):
            raise ValueError("Task-5 canonical authority is unavailable")
        prepared = canonicalize(command)
        if (
            getattr(prepared, "command", None) != command
            or not isinstance(getattr(prepared, "request", None), Mapping)
            or not isinstance(getattr(prepared, "input_sha256", None), str)
            or not isinstance(getattr(prepared, "profile_sha256", None), str)
        ):
            raise ValueError("Task-5 canonical authority is invalid")
        return prepared

    def _content_finalize_outcome(
        self,
        *,
        build_id: str,
        persisted: Mapping[str, object] | None,
        explicit_failed: bool,
    ) -> tuple[bool, Mapping[str, object]]:
        del persisted
        with self.repository.transaction() as conn:
            inventory = self.repository.load_content_proof_inventory(
                conn, build_id=build_id
            )
            build = inventory.get("build")
            failed = explicit_failed or (
                isinstance(build, Mapping)
                and str(build.get("status") or "") == "failed"
            )
            try:
                summary = self._audit_locked_content_inventory(
                    conn=conn,
                    inventory=inventory,
                )["summary"]
            except (
                PrimaryOneHostGateControlError,
                PrimaryOneHostGateDependencyError,
                KeyError,
                TypeError,
                ValueError,
            ):
                if not failed:
                    self.repository.fence_content_failure(
                        conn,
                        build_id=build_id,
                        item_id=None,
                        error_code="preparation_content_contract_drift",
                        now=self._trusted_content_now(),
                    )
                    inventory = self.repository.load_content_proof_inventory(
                        conn, build_id=build_id
                    )
                    failed = True
                summary = self._terminal_content_summary_from_inventory(
                    inventory
                )
            return failed, summary

    def _content_phase_command(
        self,
        *,
        item: Mapping[str, object],
        dispatches: Sequence[object],
        plan: Mapping[str, object],
    ) -> tuple[QuestionPhaseCommand, dict[str, object]]:
        phase = str(item["content_phase"])
        phase_ordinal = self._content_phase_ordinal(phase)
        logical_attempt = int(item["attempt_count"])
        generation_request_id = str(item["active_generation_request_id"])
        initial = self._attempt_initial_checkpoint(
            item=item, dispatches=dispatches, plan=plan
        )
        checkpoints: dict[tuple[str, int], Mapping[str, object]] = {}
        expected_predecessors: list[tuple[str, int]] = []
        for raw in dispatches:
            if not isinstance(raw, Mapping):
                raise ValueError("provider dispatch shape drift")
            row_phase = str(raw.get("phase") or "")
            ordinal = int(raw.get("phase_ordinal") or 0)
            if (
                str(raw.get("build_item_id") or "") != str(item["id"])
                or int(raw.get("logical_attempt") or 0) != logical_attempt
                or str(raw.get("generation_request_id") or "")
                != generation_request_id
                or self._content_phase_ordinal(row_phase) != ordinal
                or int(raw.get("attempt_started_at") or 0)
                != int(item["content_attempt_started_at"])
                or int(raw.get("attempt_hard_deadline_at") or 0)
                != int(item["content_provider_attempt_hard_deadline_at"])
            ):
                raise ValueError("provider dispatch identity drift")
            status = str(raw.get("status") or "")
            execution = question_phase_execution_authority(
                row_phase, ordinal
            )
            expected_profile = self._content_profile_evidence(
                str(execution["providerRole"])
            )
            if (
                str(raw.get("provider") or "") != expected_profile.name
                or str(raw.get("model") or "") != expected_profile.model
                or str(raw.get("profile") or "") != expected_profile.profile_hash
            ):
                raise ValueError("provider dispatch profile drift")
            if ordinal < phase_ordinal:
                if status != "succeeded":
                    raise ValueError("predecessor dispatch is not succeeded")
                predecessor_checkpoint = self._assemble_content_checkpoint(
                    phase=row_phase,
                    phase_ordinal=ordinal,
                    initial=initial,
                    succeeded=checkpoints,
                )
                predecessor_command = QuestionPhaseCommand(
                    build_item_id=str(item["id"]),
                    logical_attempt=logical_attempt,
                    phase=row_phase,
                    phase_ordinal=ordinal,
                    generation_request_id=generation_request_id,
                    grade_code=preparation_authority_grade(item),
                    subject=str(item["subject"]),
                    instruction_language_code="zh-CN",
                    target_language_code=(
                        "en-US"
                        if str(item["subject"]) == "english"
                        else "zh-CN"
                    ),
                    difficulty_code=self._content_target(item).difficulty_code,
                    boundary=self._content_boundary(item),
                    checkpoint=predecessor_checkpoint,
                )
                prepared = self._content_provider_preflight(
                    predecessor_command
                )
                if prepared.input_sha256 != str(raw.get("input_sha256") or ""):
                    raise ValueError("provider predecessor input hash drift")
                checkpoint = self._decode_content_json(raw.get("checkpoint_json"))
                output_hash = hashlib.sha256(
                    self._canonical_content_json(checkpoint).encode("utf-8")
                ).hexdigest()
                if output_hash != str(raw.get("output_sha256") or ""):
                    raise ValueError("provider checkpoint hash drift")
                checkpoints[(row_phase, ordinal)] = checkpoint
                expected_predecessors.append((row_phase, ordinal))
            elif ordinal == phase_ordinal:
                if row_phase != phase:
                    raise ValueError("current dispatch phase drift")
            else:
                raise ValueError("future provider dispatch drift")
        if expected_predecessors:
            expected = self._executed_content_chain(checkpoints)
            if expected != expected_predecessors:
                raise ValueError("provider branch chain drift")
        checkpoint = self._assemble_content_checkpoint(
            phase=phase,
            phase_ordinal=phase_ordinal,
            initial=initial,
            succeeded=checkpoints,
        )
        command = QuestionPhaseCommand(
            build_item_id=str(item["id"]),
            logical_attempt=logical_attempt,
            phase=phase,
            phase_ordinal=phase_ordinal,
            generation_request_id=generation_request_id,
            grade_code=preparation_authority_grade(item),
            subject=str(item["subject"]),
            instruction_language_code=(
                "zh-CN"
            ),
            target_language_code=(
                "en-US" if str(item["subject"]) == "english" else "zh-CN"
            ),
            difficulty_code=self._content_target(item).difficulty_code,
            boundary=self._content_boundary(item),
            checkpoint=checkpoint,
        )
        return command, initial

    @staticmethod
    def _content_phase_ordinal(phase: str) -> int:
        for authority in QUESTION_PHASE_IO:
            if str(authority["phase"]) == phase:
                return int(authority["phaseOrdinal"])
        raise ValueError("unsupported content phase")

    def _attempt_initial_checkpoint(
        self,
        *,
        item: Mapping[str, object],
        dispatches: Sequence[object],
        plan: Mapping[str, object],
    ) -> dict[str, object]:
        checkpoint, _authoritative_fingerprints = (
            self._attempt_question_fingerprint_authority(
                item=item,
                dispatches=dispatches,
                plan=plan,
            )
        )
        return checkpoint

    def _attempt_question_fingerprint_authority(
        self,
        *,
        item: Mapping[str, object],
        dispatches: Sequence[object],
        plan: Mapping[str, object],
    ) -> tuple[dict[str, object], list[str]]:
        prior_raw = plan.get("priorEvidence")
        if not isinstance(prior_raw, Sequence):
            raise ValueError("prior content evidence is unavailable")
        historical_raw = plan.get("historicalQuestionFingerprints")
        if not isinstance(historical_raw, list):
            raise ValueError("historical question fingerprint snapshot is unavailable")
        historical_fingerprints = [str(value) for value in historical_raw]
        if (
            historical_fingerprints != sorted(set(historical_fingerprints))
            or any(
                re.fullmatch(r"[0-9a-f]{64}", value) is None
                for value in historical_fingerprints
            )
        ):
            raise ValueError("historical question fingerprint snapshot drift")
        prior = list(prior_raw)
        expected_prior_count = int(item["variant_ordinal"]) - 1
        if len(prior) != expected_prior_count:
            raise ValueError("prior content evidence count drift")
        fingerprints: list[str] = []
        for evidence in prior:
            if not isinstance(evidence, Mapping):
                raise ValueError("prior content evidence shape drift")
            prior_item = evidence.get("item")
            if not isinstance(prior_item, Mapping):
                raise ValueError("prior content item evidence drift")
            prior_attempt = (
                self._locked_attempt_evidence(
                    evidence=evidence,
                    attempt=int(prior_item.get("attempt_count") or 0),
                )
                if "attemptHistories" in evidence
                else evidence
            )
            final = self._final_checkpoint_from_dispatches(
                prior_attempt.get("dispatches")
            )
            raw_fingerprints = final["questionFingerprints"]
            if not isinstance(raw_fingerprints, list) or len(raw_fingerprints) != 5:
                raise ValueError("prior question fingerprint evidence drift")
            fingerprints.extend(
                str(value["fingerprint"])
                for value in raw_fingerprints
                if isinstance(value, Mapping)
            )
        feedback = None
        candidate_less_attempt_one = False
        if int(item["attempt_count"]) == 2:
            attempt_one = plan.get("attemptOneEvidence")
            if not isinstance(attempt_one, Mapping):
                raise ValueError("attempt-one evidence is missing")
            candidate_less_attempt_one = (
                recovery_dispatches(item=item, evidence=attempt_one) is not None
                or
                self._zero_call_number_sense_attempt_one_dispatches(
                    item=item, evidence=attempt_one
                )
                is not None
                or self._provider_rejected_addition_subtraction_attempt_one_dispatches(
                    item=item, evidence=attempt_one
                )
                is not None
            )
            if not candidate_less_attempt_one:
                if "attemptHistories" in attempt_one:
                    attempt_one = self._locked_attempt_evidence(
                        evidence=attempt_one,
                        attempt=1,
                    )
                final = self._final_checkpoint_from_dispatches(
                    attempt_one.get("dispatches")
                )
                raw_fingerprints = final["questionFingerprints"]
                if (
                    not isinstance(raw_fingerprints, list)
                    or len(raw_fingerprints) != 5
                ):
                    raise ValueError("attempt-one fingerprint evidence drift")
                fingerprints.extend(
                    str(value["fingerprint"])
                    for value in raw_fingerprints
                    if isinstance(value, Mapping)
                )
                candidate = attempt_one.get("candidate")
                if not isinstance(candidate, Mapping):
                    raise ValueError("attempt-one candidate evidence drift")
                envelope = self._decode_content_json(
                    candidate.get("validation_json")
                )
                receipt = envelope.get("hostGateReceipt")
                issues = (
                    receipt.get("issues") if isinstance(receipt, Mapping) else None
                )
                first_issue = (
                    issues[0] if isinstance(issues, list) and issues else None
                )
                code = (
                    str(first_issue.get("code") or "")
                    if isinstance(first_issue, Mapping)
                    else ""
                )
                message = (
                    str(first_issue.get("message") or "")
                    if isinstance(first_issue, Mapping)
                    else ""
                )
                if not code or not message:
                    raise ValueError("attempt-one safe feedback is missing")
                feedback = {"code": code, "message": message}
        local_fingerprints = sorted(set(fingerprints))
        if len(local_fingerprints) != expected_prior_count * 5 + (
            5
            if int(item["attempt_count"]) == 2 and not candidate_less_attempt_one
            else 0
        ):
            raise ValueError("prior question fingerprints are not unique")
        authoritative_fingerprints = sorted(
            set(historical_fingerprints) | set(local_fingerprints)
        )
        provider_fingerprints = provider_question_fingerprint_projection(
            authoritative_fingerprints=authoritative_fingerprints,
            required_fingerprints=local_fingerprints,
            request_id=str(item.get("active_generation_request_id") or ""),
        )
        initial = {
            "questionCount": 5,
            "existingFingerprints": provider_fingerprints,
            "generationFeedback": feedback,
        }
        # Provider input remains within the sidecar's 500-item schema.  Host
        # validation receives the complete immutable snapshot separately, so
        # trimming transport does not permit an old question to be accepted.
        return initial, authoritative_fingerprints

    @staticmethod
    def _zero_call_number_sense_attempt_one_dispatches(
        *,
        item: Mapping[str, object],
        evidence: Mapping[str, object],
    ) -> Sequence[Mapping[str, object]] | None:
        """Validate the immutable zero-Provider attempt-one recovery proof."""

        evidence_item = evidence.get("item")
        dispatches: object = evidence.get("dispatches")
        if "attemptHistories" in evidence:
            histories = evidence.get("attemptHistories")
            history = histories.get(1) if isinstance(histories, Mapping) else None
            if not isinstance(history, Mapping) or any(
                history.get(key) for key in ("jobs", "candidates", "courses")
            ):
                return None
            if str(history.get("requestId") or "") != str(
                item.get("generation_request_id") or ""
            ):
                return None
            dispatches = history.get("dispatches")
        elif str(evidence.get("recoveryKind") or "") not in {
            "zero_call_number_sense_preflight.v1",
            "zero_call_canonical_host_preflight.v1",
        }:
            return None
        request_id = str(item.get("generation_request_id") or "")
        if (
            not isinstance(evidence_item, Mapping)
            or str(evidence_item.get("id") or "") != str(item.get("id") or "")
            or str(evidence_item.get("generation_request_id") or "") != request_id
            or str(item.get("grade_code") or "") != "primary_1"
            or (
                str(item.get("subject") or ""),
                str(item.get("skill_id") or ""),
            )
            not in {("math", "number_sense_20"), ("english", "letters_sounds")}
            or int(item.get("attempt_count") or 0) != 2
            or str(item.get("active_generation_request_id") or "")
            != request_id + ".attempt2"
            or not isinstance(dispatches, Sequence)
            or len(dispatches) != 3
        ):
            return None
        expected = (
            ("outline", 1, "succeeded"),
            ("raw_candidate", 2, "succeeded"),
            ("candidate_repair", 3, "failed_safe"),
        )
        if any(
            not isinstance(dispatch, Mapping)
            or str(dispatch.get("phase") or "") != phase
            or int(dispatch.get("phase_ordinal") or 0) != ordinal
            or str(dispatch.get("status") or "") != status
            or int(dispatch.get("logical_attempt") or 0) != 1
            or str(dispatch.get("generation_request_id") or "") != request_id
            or re.fullmatch(
                r"[0-9a-f]{64}", str(dispatch.get("input_sha256") or "")
            )
            is None
            for dispatch, (phase, ordinal, status) in zip(dispatches, expected)
        ):
            return None
        if any(
            dispatch.get("checkpoint_json") is None
            or re.fullmatch(
                r"[0-9a-f]{64}", str(dispatch.get("output_sha256") or "")
            )
            is None
            for dispatch in dispatches[:2]
        ):
            return None
        failed = dispatches[-1]
        if not isinstance(failed, Mapping) or not (
            str(failed.get("safe_error_code") or "")
            == "question_phase_preflight_rejected"
            and failed.get("provider_request_id_hash") is None
            and failed.get("input_tokens") is None
            and failed.get("output_tokens") is None
            and str(failed.get("billing_evidence") or "") == "unknown"
            and failed.get("checkpoint_json") is None
            and failed.get("output_sha256") is None
        ):
            return None
        return list(dispatches)

    def _provider_rejected_addition_subtraction_attempt_one_dispatches(
        self,
        *,
        item: Mapping[str, object],
        evidence: Mapping[str, object],
    ) -> Sequence[Mapping[str, object]] | None:
        evidence_item = evidence.get("item")
        if (
            not isinstance(evidence_item, Mapping)
            or str(evidence_item.get("id") or "") != str(item.get("id") or "")
            or str(evidence_item.get("generation_request_id") or "")
            != str(item.get("generation_request_id") or "")
        ):
            return None
        histories = evidence.get("attemptHistories")
        if not isinstance(histories, Mapping):
            if str(evidence.get("recoveryKind") or "") != (
                "provider_rejected_addition_subtraction_retry.v1"
            ):
                return None
            histories = {
                1: {
                    "requestId": str(item.get("generation_request_id") or ""),
                    "dispatches": evidence.get("dispatches"),
                    "jobs": [],
                    "candidates": [],
                    "courses": [],
                }
            }
        normalized = self.repository._provider_rejected_addition_subtraction_attempt_one_evidence_from_histories(
            item=item,
            histories=histories,
        )
        dispatches = normalized.get("dispatches") if normalized is not None else None
        return list(dispatches) if isinstance(dispatches, Sequence) else None

    def _assemble_content_checkpoint(
        self,
        *,
        phase: str,
        phase_ordinal: int,
        initial: Mapping[str, object],
        succeeded: Mapping[tuple[str, int], Mapping[str, object]],
    ) -> dict[str, object]:
        io = next(
            authority
            for authority in QUESTION_PHASE_IO
            if str(authority["phase"]) == phase
            and int(authority["phaseOrdinal"]) == phase_ordinal
        )
        transition = next(
            authority
            for authority in QUESTION_PHASE_TRANSITIONS
            if str(authority["phase"]) == phase
            and int(authority["phaseOrdinal"]) == phase_ordinal
        )
        checkpoint: dict[str, object] = {}
        artifacts = {
            str(value["currentInputKey"]): value
            for value in transition["requiredSucceededArtifacts"]
        }
        for key_value in io["inputCheckpointKeys"]:
            key = str(key_value)
            if key in initial:
                checkpoint[key] = initial[key]
                continue
            artifact = artifacts.get(key)
            if artifact is not None:
                selected = None
                for source in artifact["sources"]:
                    source_key = (
                        str(source["phase"]),
                        int(source["phaseOrdinal"]),
                    )
                    source_checkpoint = succeeded.get(source_key)
                    if (
                        source_checkpoint is not None
                        and source_checkpoint.get("phaseStatus")
                        == source["phaseStatus"]
                        and source["outputKey"] in source_checkpoint
                    ):
                        selected = source_checkpoint[source["outputKey"]]
                if selected is None:
                    raise ValueError("required provider artifact is missing")
                checkpoint[key] = selected
                continue
            if key == "leakingQuestionIndexes":
                checkpoint[key] = self._practice_leak_indexes(
                    checkpoint["lessonText"], checkpoint["reconciliation"]
                )
            elif key == "violatingQuestionIndexes":
                checkpoint[key] = self._choice_violation_indexes(
                    checkpoint["reconciliation"]
                )
            elif key == "reviewIssues":
                solution = checkpoint.get("independentSolution")
                review = (
                    solution.get("teachingReview")
                    if isinstance(solution, Mapping)
                    else None
                )
                issues = review.get("issues") if isinstance(review, Mapping) else None
                if not isinstance(issues, list) or not issues:
                    raise ValueError("teaching review issues are missing")
                checkpoint[key] = issues
            else:
                raise ValueError("provider checkpoint authority is incomplete")
        return checkpoint

    def _executed_content_chain(
        self,
        checkpoints: Mapping[tuple[str, int], Mapping[str, object]],
    ) -> list[tuple[str, int]]:
        current = ("outline", 1)
        chain: list[tuple[str, int]] = []
        while current in checkpoints:
            chain.append(current)
            next_phase = self._next_content_phase(
                current[0], current[1], checkpoints[current], succeeded=checkpoints
            )
            if next_phase is None:
                break
            current = next_phase
        return chain

    def _next_content_phase(
        self,
        phase: str,
        ordinal: int,
        checkpoint: Mapping[str, object],
        *,
        succeeded: Mapping[tuple[str, int], Mapping[str, object]] | None = None,
    ) -> tuple[str, int] | None:
        status = str(checkpoint.get("phaseStatus") or "")
        if status not in {"accepted", "rejected"}:
            raise ValueError("phase checkpoint status drift")
        current = next(
            (
                authority
                for authority in QUESTION_PHASE_TRANSITIONS
                if str(authority["phase"]) == phase
                and int(authority["phaseOrdinal"]) == int(ordinal)
            ),
            None,
        )
        if current is None:
            raise ValueError("unsupported provider phase")
        checkpoints = dict(succeeded or {})
        checkpoints[(phase, int(ordinal))] = checkpoint
        for transition in sorted(
            QUESTION_PHASE_TRANSITIONS,
            key=lambda authority: int(authority["phaseOrdinal"]),
        ):
            next_ordinal = int(transition["phaseOrdinal"])
            if next_ordinal <= int(ordinal):
                continue
            if self._content_transition_predicate_holds(
                transition, checkpoints
            ):
                return str(transition["phase"]), next_ordinal

        terminal_ordinal = max(
            int(authority["phaseOrdinal"])
            for authority in QUESTION_PHASE_TRANSITIONS
        )
        if int(ordinal) == terminal_ordinal:
            return None
        review_transitions = [
            authority
            for authority in QUESTION_PHASE_TRANSITIONS
            if str(authority["branchPredicate"])
            == "phase_11_teaching_review_failed"
        ]
        if len(review_transitions) == 1:
            solution = self._content_transition_artifact_value(
                review_transitions[0], "independentSolution", checkpoints
            )
            review = (
                solution.get("teachingReview")
                if isinstance(solution, Mapping)
                else None
            )
            if (
                isinstance(review, Mapping)
                and review.get("passed") is True
                and any(
                    str(source["phase"]) == phase
                    and int(source["phaseOrdinal"]) == int(ordinal)
                    for artifact in review_transitions[0][
                        "requiredSucceededArtifacts"
                    ]
                    for source in artifact["sources"]
                )
            ):
                return None
        raise ValueError("provider graph has no authorized next transition")

    @staticmethod
    def _content_transition_artifact_value(
        transition: Mapping[str, object],
        key: str,
        checkpoints: Mapping[tuple[str, int], Mapping[str, object]],
    ) -> object | None:
        artifacts = transition.get("requiredSucceededArtifacts")
        if not isinstance(artifacts, Sequence):
            return None
        selected: object | None = None
        for artifact in artifacts:
            if (
                not isinstance(artifact, Mapping)
                or str(artifact.get("currentInputKey") or "") != key
            ):
                continue
            sources = artifact.get("sources")
            if not isinstance(sources, Sequence):
                return None
            for source in sources:
                if not isinstance(source, Mapping):
                    continue
                source_checkpoint = checkpoints.get(
                    (
                        str(source.get("phase") or ""),
                        int(source.get("phaseOrdinal") or 0),
                    )
                )
                output_key = str(source.get("outputKey") or "")
                if (
                    isinstance(source_checkpoint, Mapping)
                    and source_checkpoint.get("phaseStatus")
                    == source.get("phaseStatus")
                    and output_key in source_checkpoint
                ):
                    selected = source_checkpoint[output_key]
        return selected

    @classmethod
    def _content_transition_artifacts_available(
        cls,
        transition: Mapping[str, object],
        checkpoints: Mapping[tuple[str, int], Mapping[str, object]],
    ) -> bool:
        artifacts = transition.get("requiredSucceededArtifacts")
        if not isinstance(artifacts, Sequence):
            return False
        return all(
            isinstance(artifact, Mapping)
            and cls._content_transition_artifact_value(
                transition,
                str(artifact.get("currentInputKey") or ""),
                checkpoints,
            )
            is not None
            for artifact in artifacts
        )

    def _content_transition_predicate_holds(
        self,
        transition: Mapping[str, object],
        checkpoints: Mapping[tuple[str, int], Mapping[str, object]],
    ) -> bool:
        predicate = str(transition.get("branchPredicate") or "")
        if predicate in {"initial", "always"}:
            return True
        if predicate.endswith("_rejected"):
            return self._content_transition_artifact_value(
                transition, "priorRejectionCode", checkpoints
            ) is not None
        if predicate in {
            "latest_reconciliation_has_practice_leaks",
            "phase_8_reconciliation_still_has_practice_leaks",
            "latest_reconciliation_has_choice_prompt_violations",
            "latest_reconciliation_is_clean",
        }:
            reconciliation = self._content_transition_artifact_value(
                transition, "reconciliation", checkpoints
            )
            lesson = self._content_transition_artifact_value(
                transition, "lessonText", checkpoints
            )
            leaks = bool(self._practice_leak_indexes(lesson, reconciliation))
            choices = bool(self._choice_violation_indexes(reconciliation))
            if predicate.endswith("practice_leaks"):
                return leaks
            if predicate.endswith("choice_prompt_violations"):
                return choices
            return not leaks and not choices
        if predicate in {
            "phase_11_teaching_review_failed",
            "phase_11_teaching_review_failed_and_consistency_repair_accepted",
        }:
            review_authority = next(
                (
                    authority
                    for authority in QUESTION_PHASE_TRANSITIONS
                    if str(authority["branchPredicate"])
                    == "phase_11_teaching_review_failed"
                ),
                None,
            )
            solution = (
                self._content_transition_artifact_value(
                    review_authority, "independentSolution", checkpoints
                )
                if isinstance(review_authority, Mapping)
                else None
            )
            review = (
                solution.get("teachingReview")
                if isinstance(solution, Mapping)
                else None
            )
            if not isinstance(review, Mapping) or not isinstance(
                review.get("passed"), bool
            ):
                raise ValueError("teaching review drift")
            if (
                predicate
                == "phase_11_teaching_review_failed_and_consistency_repair_accepted"
                and self._content_transition_artifact_value(
                    transition, "repair", checkpoints
                )
                is None
            ):
                return False
            return review["passed"] is False
        raise ValueError("unsupported provider transition predicate")

    def _succeeded_content_checkpoints(
        self, dispatches: Sequence[object]
    ) -> dict[tuple[str, int], Mapping[str, object]]:
        result: dict[tuple[str, int], Mapping[str, object]] = {}
        for row in dispatches:
            if not isinstance(row, Mapping) or row.get("status") != "succeeded":
                continue
            checkpoint = self._decode_content_json(row.get("checkpoint_json"))
            result[(str(row["phase"]), int(row["phase_ordinal"]))] = checkpoint
        return result

    @staticmethod
    def _choice_violation_indexes(reconciliation: object) -> list[int]:
        questions = (
            reconciliation.get("questions")
            if isinstance(reconciliation, Mapping)
            else None
        )
        if not isinstance(questions, list):
            return []
        violations: list[int] = []
        for index, question in enumerate(questions):
            if (
                not isinstance(question, Mapping)
                or question.get("type") != "single_choice"
            ):
                continue
            choices = question.get("choices")
            if not isinstance(choices, list):
                continue
            prompt = unicodedata.normalize(
                "NFKC", str(question.get("prompt") or "")
            )
            occurrences: list[tuple[int, int]] = []
            for choice in choices:
                if not isinstance(choice, Mapping):
                    continue
                label = unicodedata.normalize(
                    "NFKC", str(choice.get("label") or "")
                ).strip()
                comparable = LearningCatalogReleaseService._content_comparable(
                    label
                )
                if len(re.sub(r"\s+", "", comparable)) < 2:
                    continue
                start = prompt.find(label)
                if start >= 0:
                    occurrences.append((start, start + len(label)))
            occurrences.sort()
            for left, right in zip(occurrences, occurrences[1:]):
                between = prompt[left[1] : right[0]]
                if re.fullmatch(r"[\s、,，;；/／|]+", between):
                    violations.append(index)
                    break
        return violations

    @classmethod
    def _practice_leak_indexes(
        cls, lesson: object, reconciliation: object
    ) -> list[int]:
        questions = (
            reconciliation.get("questions")
            if isinstance(reconciliation, Mapping)
            else None
        )
        flow = lesson.get("teachingFlow") if isinstance(lesson, Mapping) else None
        if not isinstance(questions, list) or not isinstance(flow, Mapping):
            return []
        teach = flow.get("teach")
        recap = flow.get("recap")
        texts: list[str] = []
        if isinstance(teach, Mapping):
            for key in ("title", "sayText"):
                if isinstance(teach.get(key), str):
                    texts.append(str(teach[key]))
            key_points = teach.get("keyPoints")
            if isinstance(key_points, list):
                texts.extend(
                    str(value) for value in key_points if isinstance(value, str)
                )
        if isinstance(recap, Mapping) and isinstance(recap.get("sayText"), str):
            texts.append(str(recap["sayText"]))
        return [
            index
            for index, question in enumerate(questions)
            if index > 0
            and isinstance(question, Mapping)
            and any(
                cls._content_teaching_reveals_question(
                    text, question, index + 1
                )
                for text in texts
            )
        ]

    @staticmethod
    def _content_comparable(value: object) -> str:
        normalized = unicodedata.normalize("NFKC", str(value))
        normalized = re.sub(
            r"[\u0009-\u000D\u0020\u00A0\u1680\u2000-\u200A"
            r"\u2028\u2029\u202F\u205F\u3000\uFEFF]+",
            " ",
            normalized,
        )
        return normalized.strip().lower()

    @classmethod
    def _content_answer_values(
        cls, question: Mapping[str, object]
    ) -> list[str]:
        question_type = question.get("type")
        if question_type == "accepted_text":
            answer = question.get("answer")
            return [str(value) for value in answer] if isinstance(answer, list) else []
        if question_type == "single_choice":
            choices = question.get("choices")
            if isinstance(choices, list):
                for choice in choices:
                    if (
                        isinstance(choice, Mapping)
                        and choice.get("id") == question.get("answer")
                    ):
                        return [str(choice.get("label") or "")]
            return []
        if question_type == "sequence":
            choices = question.get("choices")
            answer = question.get("answer")
            if not isinstance(choices, list) or not isinstance(answer, list):
                return []
            labels: list[str] = []
            for value in answer:
                match = next(
                    (
                        choice
                        for choice in choices
                        if isinstance(choice, Mapping)
                        and choice.get("id") == value
                    ),
                    None,
                )
                labels.append(
                    str(match.get("label") if isinstance(match, Mapping) else value)
                )
            return [" ".join(labels), "、".join(labels)]
        return [str(question.get("answer") or "")]

    @classmethod
    def _content_prompt_explicitly_reveals(
        cls, prompt_value: object, answer_value: object
    ) -> bool:
        prompt = re.sub(r"\s+", "", cls._content_comparable(prompt_value))
        answer = re.sub(r"\s+", "", cls._content_comparable(answer_value))
        if not answer:
            return False
        escaped = re.escape(answer)
        lead = (
            r"(?:正确答案(?:是|为)?|答案(?:是|为)?|结果(?:是|为)?|"
            r"应选|请选择|直接回答|等于)"
        )
        tail = r"(?:$|[,.!?;:，。！？；：])"
        if re.search(
            rf"{lead}[：:]?[“\"']?{escaped}[”\"']?{tail}",
            prompt,
            flags=re.IGNORECASE,
        ):
            return True
        return bool(
            re.search(
                rf"=[“\"']?{escaped}[”\"']?(?:$|[,.!;:，。！；：])",
                prompt,
                flags=re.IGNORECASE,
            )
        )

    @classmethod
    def _content_primary_add_sub_signature(
        cls, question: Mapping[str, object]
    ) -> tuple[str, int, int, int] | None:
        if question.get("type") == "numeric":
            match = re.fullmatch(
                r"\s*(\d{1,2})\s*([+-])\s*(\d{1,2})\s*",
                str(question.get("verificationExpression") or ""),
            )
            if match is None:
                return None
            left, operator, right = (
                int(match.group(1)),
                match.group(2),
                int(match.group(3)),
            )
            return (
                "addition" if operator == "+" else "subtraction",
                left,
                right,
                left + right if operator == "+" else left - right,
            )
        if question.get("type") != "single_choice":
            return None
        answers = cls._content_answer_values(question)
        answer_match = re.search(
            r"(?:^|\D)(\d{1,2})(?!\d)", answers[0] if answers else ""
        )
        operands = [
            int(value)
            for value in re.findall(
                r"(?:^|\D)(\d{1,2})(?!\d)",
                cls._content_comparable(question.get("prompt")),
            )
        ]
        if answer_match is None or len(operands) < 2:
            return None
        left, right = operands[:2]
        answer = int(answer_match.group(1))
        compact = re.sub(
            r"\s+", "", cls._content_comparable(question.get("prompt"))
        )
        if re.search(rf"{left}(?:\+|加(?:上)?){right}", compact):
            operation = "addition"
        elif re.search(rf"{left}(?:-|减(?:去)?){right}", compact):
            operation = "subtraction"
        elif re.search(
            r"借走|拿走|吃(?:了|掉)|还剩|剩下|送出|用掉|走了|减少", compact
        ):
            operation = "subtraction"
        elif re.search(r"又|一共|合起来|总共|增加|放进|来了|得到|再加", compact):
            operation = "addition"
        else:
            return None
        expected = left + right if operation == "addition" else left - right
        return (operation, left, right, answer) if answer == expected else None

    @staticmethod
    def _content_teaching_reveals_signature(
        text: str, signature: tuple[str, int, int, int]
    ) -> bool:
        operation, left, right, answer = signature
        pairs = [(left, right)]
        if operation == "addition" and left != right:
            pairs.append((right, left))
        operator = (
            r"(?:\+|加(?:上)?)"
            if operation == "addition"
            else r"(?:-|减(?:去)?)"
        )
        answer_link = r"(?:=|等于|是|得|得到|结果(?:是|为)?|一共(?:是|有)?)"
        return any(
            re.search(
                rf"(^|\D){a}{operator}{b}.{{0,24}}{answer_link}.{{0,4}}{answer}(?!\d)",
                text,
            )
            for a, b in pairs
        )

    @classmethod
    def _content_teaching_reveals_question(
        cls,
        text_value: str,
        question: Mapping[str, object],
        question_number: int,
    ) -> bool:
        compact_text = re.sub(r"\s+", "", cls._content_comparable(text_value))
        if not compact_text:
            return False
        signature = cls._content_primary_add_sub_signature(question)
        if signature and cls._content_teaching_reveals_signature(
            compact_text, signature
        ):
            return True
        if not any(
            cls._content_prompt_explicitly_reveals(text_value, answer)
            for answer in cls._content_answer_values(question)
        ):
            return False
        ordinal = {2: "二", 3: "三", 4: "四", 5: "五"}.get(
            question_number, ""
        )
        if re.search(
            rf"(?:第(?:{question_number}|{ordinal})道?(?:题|练习)|q{question_number})",
            compact_text,
            flags=re.IGNORECASE,
        ):
            return True
        prompt_signature = re.sub(
            r"\s+", "", cls._content_comparable(question.get("prompt"))
        )
        prompt_signature = re.sub(r"[?？。.!！]", "", prompt_signature)
        if len(prompt_signature) >= 8 and prompt_signature in compact_text:
            return True
        if question.get("type") == "numeric":
            expression = re.sub(
                r"\s+",
                "",
                cls._content_comparable(
                    question.get("verificationExpression")
                ),
            )
            if len(expression) >= 3 and expression in compact_text:
                return True
        return False

    def _content_boundary(self, item: Mapping[str, object]) -> dict[str, object]:
        boundary = formal_registered_boundary(
            preparation_authority_grade(item), str(item["subject"]), str(item["skill_id"])
        )
        payload = dict(boundary.to_openmaic_payload())
        payload.pop("language", None)
        return payload

    def _content_profile_payload(self, role: str) -> dict[str, object]:
        raw = (self.question_phase_provider_profiles or {}).get(role)
        if not isinstance(raw, Mapping):
            raise ValueError("provider profile is missing")
        return normalize_question_phase_provider_profile(raw)

    def _content_profile_evidence(
        self, role: str
    ) -> QuestionPhaseProviderProfileEvidence:
        profile = self._content_profile_payload(role)
        digest = hashlib.sha256(
            self._canonical_content_json(profile).encode("utf-8")
        ).hexdigest()
        return QuestionPhaseProviderProfileEvidence(
            name=str(profile["name"]),
            model=str(profile["model"]),
            base_url=str(profile["baseUrl"]),
            api_key_env=str(profile["apiKeyEnv"]),
            timeout_ms=int(profile["timeoutMs"]),
            max_tokens=int(profile["maxTokens"]),
            temperature=float(profile["temperature"]),
            profile_hash=digest,
        )

    def _content_target(self, item: Mapping[str, object]) -> PrimaryOneCourseTarget:
        return PrimaryOneCourseTarget(
            grade_code=preparation_authority_grade(item),
            subject=str(item["subject"]),
            subject_ordinal=int(item["subject_ordinal"]),
            skill_id=str(item["skill_id"]),
            boundary_ordinal=int(item["boundary_ordinal"]),
            boundary_version=str(item["boundary_version"]),
            variant_ordinal=int(item["variant_ordinal"]),
            instruction_language_code="zh-CN",
            target_language_code=(
                "en-US" if str(item["subject"]) == "english" else "zh-CN"
            ),
        )

    def _content_host_evidence(
        self,
        *,
        plan: Mapping[str, object],
        item: Mapping[str, object],
    ) -> tuple[
        QuestionPhaseCourseEvidence,
        PrimaryOneCourseTarget,
        PrimaryOneHostGateIdentity,
        tuple[AcceptedPrimaryOneHostReceipt, ...],
    ]:
        dispatches = plan.get("dispatches")
        candidate = plan.get("candidate")
        if not isinstance(dispatches, Sequence) or not isinstance(candidate, Mapping):
            raise ValueError("Host evidence is missing")
        self._validate_content_dispatch_chain(
            item=item, dispatches=dispatches, plan=plan
        )
        final = None
        for row in dispatches:
            if not isinstance(row, Mapping) or str(row.get("status") or "") != "succeeded":
                raise ValueError("Host provider chain is incomplete")
            phase = str(row.get("phase") or "")
            ordinal = int(row.get("phase_ordinal") or 0)
            execution = question_phase_execution_authority(phase, ordinal)
            if execution["finalCandidateKey"] is not None:
                final = row
        if final is None:
            raise ValueError("Host final provider checkpoint is missing")
        checkpoint = self._decode_content_json(final.get("checkpoint_json"))
        final_phase = str(final["phase"])
        final_ordinal = int(final["phase_ordinal"])
        course_key = question_phase_execution_authority(
            final_phase, final_ordinal
        )["finalCandidateKey"]
        if not isinstance(course_key, str):
            raise ValueError("Host final provider checkpoint is invalid")
        course = checkpoint.get(course_key)
        if not isinstance(course, Mapping):
            raise ValueError("Host candidate course is missing")
        if (
            str(candidate.get("course_id") or "") != str(course.get("id") or "")
            or str(candidate.get("course_version") or "") != str(course.get("version") or "")
            or str(candidate.get("content_json") or "")
            != self._canonical_content_json(course.get("content"))
        ):
            raise ValueError("Host candidate persistence drift")
        generator = self._content_profile_evidence("generator")
        verifier = self._content_profile_evidence("verifier")
        for row in dispatches:
            if not isinstance(row, Mapping):
                raise ValueError("provider dispatch profile evidence drift")
            phase = str(row.get("phase") or "")
            ordinal = int(row.get("phase_ordinal") or 0)
            role = question_phase_execution_authority(
                phase, ordinal
            )["providerRole"]
            expected = verifier if role == "verifier" else generator
            if (
                str(row.get("provider") or "") != expected.name
                or str(row.get("model") or "") != expected.model
                or str(row.get("profile") or "") != expected.profile_hash
            ):
                raise ValueError("provider dispatch profile drift")
        target = self._content_target(item)
        initial_checkpoint, authoritative_fingerprints = (
            self._attempt_question_fingerprint_authority(
                item=item,
                dispatches=dispatches,
                plan=plan,
            )
        )
        evidence = QuestionPhaseCourseEvidence(
            final_phase=str(final["phase"]),
            final_phase_ordinal=final_ordinal,
            candidate_course=course,
            question_fingerprints=checkpoint["questionFingerprints"],
            validation=checkpoint["validation"],
            independent_solution=checkpoint["independentSolution"],
            generator_profile=generator,
            verifier_profile=verifier,
            existing_fingerprint_count=len(
                initial_checkpoint["existingFingerprints"]
            ),
            authoritative_existing_fingerprints=authoritative_fingerprints,
        )
        identity = PrimaryOneHostGateIdentity(
            catalog_item_id=str(item["id"]),
            logical_attempt=int(item["attempt_count"]),
            generation_request_id=str(item["active_generation_request_id"]),
            course_id=str(course["id"]),
            course_version=str(course["version"]),
            curriculum_version=PRIMARY_CURRICULUM_VERSION,
            content_validation_contract_version=formal_content_validation_identity(target.grade_code)["contentValidationContractVersion"],
            content_validation_dataset_sha256=formal_content_validation_identity(target.grade_code)["contentValidationDatasetSha256"],
            subject_language_policy_version=SUBJECT_LANGUAGE_POLICY_VERSION,
            generator_profile_hash=generator.profile_hash,
            verifier_profile_hash=verifier.profile_hash,
        )
        prior = self._accepted_content_proofs(plan.get("priorEvidence"))
        if len(prior) != target.variant_ordinal - 1:
            raise ValueError("prior accepted Host receipt count drift")
        for proof in prior:
            self.primary_one_host_validator.validate_primary_one_accepted_receipt(
                proof
            )
        return evidence, target, identity, prior

    def audit_content_dispatch_graph(
        self,
        *,
        item: Mapping[str, object],
        dispatches: Sequence[object],
    ) -> ContentDispatchGraphAuditSnapshot:
        snapshot, _checkpoints = self._validated_content_dispatch_graph(
            item=item,
            dispatches=dispatches,
        )
        return snapshot

    def audit_content_host_retry_graph(
        self,
        *,
        evidence: Mapping[str, object],
        prior_evidence: Sequence[Mapping[str, object]],
    ) -> ContentDispatchGraphAuditSnapshot:
        if not isinstance(evidence, Mapping) or not isinstance(
            prior_evidence, Sequence
        ):
            raise ValueError("Host retry graph evidence is incomplete")
        item = evidence.get("item")
        if not isinstance(item, Mapping):
            raise ValueError("Host retry graph item is missing")
        attempt = int(item.get("attempt_count") or 0)
        request_id = str(item.get("generation_request_id") or "") + (
            ".attempt2" if attempt == 2 else ""
        )
        if (
            str(item.get("status") or "") != "processing"
            or str(item.get("content_phase") or "")
            not in {"host_gate_pending", "host_gate_running"}
            or str(item.get("content_gate_status") or "")
            not in {"pending", "retry_wait"}
            or attempt not in {1, 2}
            or not request_id
            or str(item.get("active_generation_request_id") or "")
            != request_id
            or not self._host_retry_item_authority_is_exact(
                item=item,
                attempt=attempt,
            )
        ):
            raise ValueError("Host retry graph item authority drift")
        if attempt == 1:
            self._require_empty_locked_attempt_history(
                evidence=evidence,
                attempt=2,
            )
        current = self._locked_host_pending_attempt_evidence(
            evidence=evidence,
            attempt=attempt,
        )
        candidate = current.get("candidate")
        job = current.get("job")
        dispatches = current.get("dispatches")
        if (
            not isinstance(candidate, Mapping)
            or not isinstance(job, Mapping)
            or not isinstance(dispatches, Sequence)
        ):
            raise ValueError("Host retry graph persistence drift")
        attempt_one = None
        if attempt == 2:
            if recovery_dispatches(item=item, evidence=evidence) is not None:
                attempt_one = evidence
            else:
                attempt_one = self._locked_attempt_evidence(
                    evidence=evidence,
                    attempt=1,
                )
                self._validate_locked_rejected_history(
                    evidence=evidence,
                    item=item,
                    history_evidence=attempt_one,
                    prior_evidence=prior_evidence,
                )
        plan = {
            "candidate": candidate,
            "dispatches": dispatches,
            "historicalQuestionFingerprints": current.get(
                "historicalQuestionFingerprints"
            ),
            "priorEvidence": prior_evidence,
            "attemptOneEvidence": evidence if attempt_one is not None else None,
        }
        host_evidence, _target, _identity, _priors = self._content_host_evidence(
            plan=plan,
            item=item,
        )
        self._validate_locked_host_pending_persistence(
            evidence=current,
            item=item,
            candidate_course=host_evidence.candidate_course,
            attempt_one_evidence=attempt_one,
        )
        return self.audit_content_dispatch_graph(
            item=item,
            dispatches=dispatches,
        )

    @staticmethod
    def _host_retry_item_authority_is_exact(
        *,
        item: Mapping[str, object],
        attempt: int,
    ) -> bool:
        if any(
            type(item.get(field)) is not int
            for field in (
                "attempt_count",
                "content_claim_attempt_ordinal",
                "content_gate_attempt_count",
                "content_attempt_started_at",
            )
        ):
            return False
        phase = str(item.get("content_phase") or "")
        gate_count = int(item["content_gate_attempt_count"])
        common = bool(
            int(item["attempt_count"]) == attempt
            and int(item["content_claim_attempt_ordinal"]) == attempt
            and int(item["content_attempt_started_at"]) > 0
            and item.get("content_provider_attempt_hard_deadline_at") is None
            and item.get("content_gate_passed_at") is None
            and item.get("content_validation_contract_version") is None
            and item.get("content_receipt_hash") is None
        )
        if not common:
            return False
        if phase == "host_gate_pending":
            return bool(
                str(item.get("content_gate_status") or "")
                in {"pending", "retry_wait"}
                and 0 <= gate_count <= 2
                and item.get("content_lease_token") is None
                and item.get("content_lease_expires_at") is None
                and item.get("content_heartbeat_at") is None
                and item.get("content_work_unit_deadline_at") is None
            )
        token = item.get("content_lease_token")
        lease = item.get("content_lease_expires_at")
        heartbeat = item.get("content_heartbeat_at")
        deadline = item.get("content_work_unit_deadline_at")
        return bool(
            phase == "host_gate_running"
            and str(item.get("content_gate_status") or "")
            in {"pending", "retry_wait"}
            and 1 <= gate_count <= 3
            and isinstance(token, str)
            and bool(token)
            and type(lease) is int
            and type(heartbeat) is int
            and type(deadline) is int
            and int(lease) == int(deadline)
            and 0 <= int(heartbeat) < int(deadline)
        )

    def _validated_content_dispatch_graph(
        self,
        *,
        item: Mapping[str, object],
        dispatches: Sequence[object],
    ) -> tuple[
        ContentDispatchGraphAuditSnapshot,
        Mapping[tuple[str, int], Mapping[str, object]],
    ]:
        if not isinstance(item, Mapping) or not isinstance(dispatches, Sequence):
            raise ValueError("provider dispatch graph input drift")
        item_id = str(item.get("id") or "")
        logical_attempt = int(item.get("attempt_count") or 0)
        generation_request_id = str(
            item.get("active_generation_request_id") or ""
        )
        if (
            not item_id
            or logical_attempt not in {1, 2}
            or not generation_request_id
        ):
            raise ValueError("provider dispatch graph item identity drift")
        checkpoints: dict[tuple[str, int], Mapping[str, object]] = {}
        ordered: list[tuple[str, int]] = []
        dispatch_ids: list[str] = []
        attempt_started_at: int | None = None
        hard_deadline_at: int | None = None
        item_attempt_started_at = int(
            item.get("content_attempt_started_at") or 0
        )
        raw_item_hard_deadline = item.get(
            "content_provider_attempt_hard_deadline_at"
        )
        item_hard_deadline_at = (
            int(raw_item_hard_deadline)
            if raw_item_hard_deadline is not None
            else None
        )
        if item_attempt_started_at <= 0:
            raise ValueError("provider dispatch item deadline authority drift")
        for row in dispatches:
            if not isinstance(row, Mapping):
                raise ValueError("provider dispatch chain shape drift")
            dispatch_id = str(row.get("id") or "")
            phase = str(row.get("phase") or "")
            ordinal = int(row.get("phase_ordinal") or 0)
            if (
                not dispatch_id
                or str(row.get("status") or "") != "succeeded"
                or self._content_phase_ordinal(phase) != ordinal
                or str(row.get("build_item_id") or "") != item_id
                or int(row.get("logical_attempt") or 0)
                != logical_attempt
                or str(row.get("generation_request_id") or "")
                != generation_request_id
            ):
                raise ValueError("provider dispatch chain identity drift")
            row_attempt_started = int(row.get("attempt_started_at") or 0)
            row_hard_deadline = int(row.get("attempt_hard_deadline_at") or 0)
            if attempt_started_at is None:
                attempt_started_at = row_attempt_started
                hard_deadline_at = row_hard_deadline
                if item_hard_deadline_at is None:
                    item_hard_deadline_at = row_hard_deadline
            if (
                row_attempt_started != attempt_started_at
                or row_hard_deadline != hard_deadline_at
                or row_attempt_started <= 0
                or not provider_attempt_deadline_is_valid(
                    row_attempt_started, row_hard_deadline
                )
                or row_attempt_started != item_attempt_started_at
                or row_hard_deadline != item_hard_deadline_at
            ):
                raise ValueError("provider dispatch deadline identity drift")
            checkpoint = self._decode_content_json(row.get("checkpoint_json"))
            if hashlib.sha256(
                self._canonical_content_json(checkpoint).encode("utf-8")
            ).hexdigest() != str(row.get("output_sha256") or ""):
                raise ValueError("provider dispatch output hash drift")
            key = (phase, ordinal)
            if key in checkpoints:
                raise ValueError("duplicate provider dispatch phase")
            checkpoints[key] = checkpoint
            ordered.append(key)
            dispatch_ids.append(dispatch_id)
        if len(set(dispatch_ids)) != len(dispatch_ids):
            raise ValueError("duplicate provider dispatch identity")
        if ordered != sorted(ordered, key=lambda value: value[1]):
            raise ValueError("provider dispatch ordinal order drift")
        if self._executed_content_chain(checkpoints) != ordered:
            raise ValueError("provider dispatch authenticated graph drift")
        progressive: dict[tuple[str, int], Mapping[str, object]] = {}
        for index, key in enumerate(ordered):
            progressive[key] = checkpoints[key]
            next_key = self._next_content_phase(
                key[0],
                key[1],
                checkpoints[key],
                succeeded=progressive,
            )
            expected_next = (
                ordered[index + 1] if index + 1 < len(ordered) else None
            )
            if next_key != expected_next:
                raise ValueError("provider dispatch conditional graph drift")
            if next_key is not None:
                transition = next(
                    (
                        authority
                        for authority in QUESTION_PHASE_TRANSITIONS
                        if str(authority["phase"]) == next_key[0]
                        and int(authority["phaseOrdinal"]) == next_key[1]
                    ),
                    None,
                )
                if (
                    transition is None
                    or not self._content_transition_artifacts_available(
                        transition,
                        progressive,
                    )
                ):
                    raise ValueError(
                        "provider dispatch conditional artifacts drift"
                    )
        if not ordered or question_phase_execution_authority(
            ordered[-1][0], ordered[-1][1]
        )["finalCandidateKey"] is None:
            raise ValueError("provider dispatch graph is incomplete")
        if self._next_content_phase(
            ordered[-1][0],
            ordered[-1][1],
            checkpoints[ordered[-1]],
            succeeded=checkpoints,
        ) is not None:
            raise ValueError("provider dispatch graph is not terminal")
        final_phase, final_ordinal = ordered[-1]
        return (
            ContentDispatchGraphAuditSnapshot(
                item_id=item_id,
                logical_attempt=logical_attempt,
                dispatch_ids=tuple(dispatch_ids),
                final_phase=final_phase,
                final_phase_ordinal=final_ordinal,
            ),
            checkpoints,
        )

    def _validate_content_dispatch_chain(
        self,
        *,
        item: Mapping[str, object],
        dispatches: Sequence[object],
        plan: Mapping[str, object],
    ) -> None:
        _snapshot, checkpoints = self._validated_content_dispatch_graph(
            item=item,
            dispatches=dispatches,
        )
        initial = self._attempt_initial_checkpoint(
            item=item, dispatches=dispatches, plan=plan
        )
        prior_checkpoints: dict[
            tuple[str, int], Mapping[str, object]
        ] = {}
        for row in dispatches:
            if not isinstance(row, Mapping):
                raise ValueError("provider dispatch chain shape drift")
            phase = str(row.get("phase") or "")
            ordinal = int(row.get("phase_ordinal") or 0)
            input_checkpoint = self._assemble_content_checkpoint(
                phase=phase,
                phase_ordinal=ordinal,
                initial=initial,
                succeeded=prior_checkpoints,
            )
            command = QuestionPhaseCommand(
                build_item_id=str(item["id"]),
                logical_attempt=int(item["attempt_count"]),
                phase=phase,
                phase_ordinal=ordinal,
                generation_request_id=str(item["active_generation_request_id"]),
                grade_code=preparation_authority_grade(item),
                subject=str(item["subject"]),
                instruction_language_code="zh-CN",
                target_language_code=(
                    "en-US" if str(item["subject"]) == "english" else "zh-CN"
                ),
                difficulty_code=self._content_target(item).difficulty_code,
                boundary=self._content_boundary(item),
                checkpoint=input_checkpoint,
            )
            prepared = self._content_provider_preflight(command)
            if prepared.input_sha256 != str(row.get("input_sha256") or ""):
                raise ValueError("provider dispatch input hash drift")
            prior_checkpoints[(phase, ordinal)] = checkpoints[(phase, ordinal)]

    def _accepted_content_proofs(
        self, raw: object
    ) -> tuple[AcceptedPrimaryOneHostReceipt, ...]:
        if not isinstance(raw, Sequence):
            raise ValueError("prior accepted content evidence is missing")
        proofs: list[AcceptedPrimaryOneHostReceipt] = []
        for evidence in raw:
            if not isinstance(evidence, Mapping):
                raise ValueError("prior accepted content proof drift")
            item = evidence.get("item")
            candidate = evidence.get("candidate")
            course_row = evidence.get("course")
            if (
                isinstance(item, Mapping)
                and (
                    not isinstance(candidate, Mapping)
                    or not isinstance(course_row, Mapping)
                )
            ):
                current = self._locked_attempt_evidence(
                    evidence=evidence,
                    attempt=int(item.get("attempt_count") or 0),
                )
                candidate = current.get("candidate")
                course_row = current.get("course")
            if not all(isinstance(value, Mapping) for value in (item, candidate, course_row)):
                raise ValueError("prior accepted content persistence drift")
            envelope = self._decode_content_json(candidate.get("validation_json"))
            if set(envelope) != {
                "schemaVersion",
                "contentFingerprint",
                "hostGateReceipt",
                "hostGateReceiptHash",
            }:
                raise ValueError("prior Host envelope shape drift")
            receipt = envelope.get("hostGateReceipt")
            receipt_hash = envelope.get("hostGateReceiptHash")
            if not isinstance(receipt, Mapping) or not isinstance(receipt_hash, str):
                raise ValueError("prior Host receipt drift")
            if hashlib.sha256(
                self._canonical_content_json(receipt).encode("utf-8")
            ).hexdigest() != receipt_hash:
                raise ValueError("prior Host receipt hash drift")
            content = self._decode_content_json(course_row.get("content_json"))
            immutable_course = {
                "id": str(course_row["id"]),
                "version": str(course_row["version"]),
                "gradeCode": str(course_row["grade_code"]),
                "subject": str(course_row["subject"]),
                "nodeCode": str(course_row["node_code"]),
                "title": str(course_row["title"]),
                "objective": str(course_row["objective"]),
                "status": "published",
                "content": content,
            }
            proofs.append(
                AcceptedPrimaryOneHostReceipt(
                    target=self._content_target(item),
                    immutable_course=immutable_course,
                    receipt=receipt,
                    receipt_hash=receipt_hash,
                )
            )
        proofs.sort(
            key=lambda value: (
                value.target.subject_ordinal,
                value.target.boundary_ordinal,
                value.target.variant_ordinal,
            )
        )
        return tuple(proofs)

    def _final_checkpoint_from_dispatches(
        self, dispatches: object
    ) -> Mapping[str, object]:
        if not isinstance(dispatches, Sequence):
            raise ValueError("provider dispatch evidence is missing")
        rows = list(dispatches)
        if not rows:
            raise ValueError("final provider checkpoint is missing")
        if any(
            not isinstance(row, Mapping)
            or str(row.get("status") or "") != "succeeded"
            for row in rows
        ):
            raise ValueError("final provider checkpoint is not terminal")
        terminal = rows[-1]
        authority = question_phase_execution_authority(
            str(terminal.get("phase") or ""),
            int(terminal.get("phase_ordinal") or 0),
        )
        if authority["finalCandidateKey"] is None:
            raise ValueError("final provider checkpoint is not terminal")
        final = self._decode_content_json(terminal.get("checkpoint_json"))
        expected_hash = hashlib.sha256(
            self._canonical_content_json(final).encode("utf-8")
        ).hexdigest()
        if expected_hash != str(terminal.get("output_sha256") or ""):
            raise ValueError("final provider checkpoint hash drift")
        return final

    def _content_summary(
        self, items: Sequence[object]
    ) -> dict[str, object]:
        result = self._empty_content_summary()
        rows = [row for row in items if isinstance(row, Mapping)]
        if not rows:
            return result
        target = canonical_preparation_target_for(rows[0])
        if len(rows) != formal_target_course_count(target) or any(preparation_authority_grade(row) != target["gradeCode"] for row in rows):
            return result
        target_counts = {subject: values["totalCourseCount"] for subject, values in target["subjectTargets"].items()}
        passed = [
            row
            for row in rows
            if row.get("_content_proof_verified") is True
            and str(row.get("status") or "") == "course_ready"
            and str(row.get("content_gate_status") or "") == "passed"
            and bool(re.fullmatch(r"[0-9a-f]{64}", str(row.get("content_receipt_hash") or "")))
        ]
        failed = [
            row
            for row in rows
            if str(row.get("status") or "") == "failed"
            and not (
                int(row.get("attempt_count") or 0) == 1
                and str(row.get("content_gate_status") or "") == "failed_deterministic"
                and row.get("_content_repair_verified") is True
            )
        ]
        progress = {}
        for subject, target_count in target_counts.items():
            progress[subject] = {
                "candidateCount": sum(1 for row in passed if row.get("subject") == subject),
                "failedCount": sum(1 for row in failed if row.get("subject") == subject),
                "targetCount": target_count,
            }
        canary_keys = {
            (row["subject"], row["skillId"], row["variantOrdinal"])
            for row in target["canaryManifest"]["targets"]
        }
        passed_canaries = sum(
            1
            for row in passed
            if (row.get("subject"), row.get("skill_id"), int(row.get("variant_ordinal") or 0)) in canary_keys
        )
        failed_canaries = sum(
            1
            for row in failed
            if (row.get("subject"), row.get("skill_id"), int(row.get("variant_ordinal") or 0)) in canary_keys
        )
        return {
            "contentCandidateItemCount": len(passed),
            "contentFailedItemCount": len(failed),
            "subjectContentProgress": progress,
            "canary": {
                "targetCount": 3,
                "candidateCount": passed_canaries,
                "failedCount": failed_canaries,
                "passed": passed_canaries == 3,
            },
            "canActivate": False,
        }

    def _content_contract_failure(
        self,
        build_id: str,
        item: Mapping[str, object],
        summary: Mapping[str, object],
    ) -> ContentAdvanceResult:
        return self._content_terminal_failure(
            build_id,
            item,
            summary,
            error_code="preparation_content_contract_drift",
        )

    def _content_terminal_failure(
        self,
        build_id: str,
        item: Mapping[str, object],
        summary: Mapping[str, object],
        *,
        error_code: str,
    ) -> ContentAdvanceResult:
        with self.repository.transaction() as conn:
            self.repository.fence_content_failure(
                conn,
                build_id=build_id,
                item_id=str(item["id"]),
                error_code=error_code,
                now=self._trusted_content_now(),
            )
        refreshed_summary = self._content_summary_after_transition(
            build_id,
            terminal_already_fenced=True,
        )
        return ContentAdvanceResult(
            "failed", build_id, str(item["id"]), refreshed_summary
        )

    def _content_summary_after_transition(
        self,
        build_id: str,
        *,
        terminal_already_fenced: bool = False,
    ) -> Mapping[str, object]:
        reread_terminal_facts = False
        with self.repository.transaction() as conn:
            if hasattr(self.repository, "load_content_proof_inventory"):
                inventory = self.repository.load_content_proof_inventory(
                    conn, build_id=build_id
                )
                try:
                    return self._audit_locked_content_inventory(
                        conn=conn,
                        inventory=inventory,
                    )["summary"]
                except (
                    PrimaryOneHostGateControlError,
                    PrimaryOneHostGateDependencyError,
                    KeyError,
                    TypeError,
                    ValueError,
                ):
                    if terminal_already_fenced:
                        return self._terminal_content_summary_from_inventory(
                            inventory
                        )
                    self.repository.fence_content_failure(
                        conn,
                        build_id=build_id,
                        item_id=None,
                        error_code="preparation_content_contract_drift",
                        now=self._trusted_content_now(),
                    )
                    reread_terminal_facts = True
            else:
                items = self.repository.load_content_summary_items(
                    conn, build_id=build_id
                )
                return self._content_summary(items)
        if not reread_terminal_facts:
            return self._empty_content_summary()
        with self.repository.transaction() as conn:
            refreshed = self.repository.load_content_proof_inventory(
                conn, build_id=build_id
            )
            try:
                return self._audit_locked_content_inventory(
                    conn=conn,
                    inventory=refreshed,
                )["summary"]
            except (
                PrimaryOneHostGateControlError,
                PrimaryOneHostGateDependencyError,
                KeyError,
                TypeError,
                ValueError,
            ):
                return self._terminal_content_summary_from_inventory(
                    refreshed
                )

    def _terminal_content_summary_from_inventory(
        self,
        inventory: Mapping[str, object],
    ) -> Mapping[str, object]:
        raw_items = inventory.get("items")
        items = (
            [item for item in raw_items if isinstance(item, Mapping)]
            if isinstance(raw_items, Sequence)
            else []
        )
        terminal_items = []
        for item in items:
            terminal = dict(item)
            if (
                str(terminal.get("status") or "") == "course_ready"
                or terminal.get("content_receipt_hash") is not None
                or str(terminal.get("content_gate_status") or "")
                in {"passed", "failed_deterministic"}
            ):
                terminal["status"] = "failed"
                terminal["_content_proof_verified"] = False
                terminal["_content_repair_verified"] = False
            terminal_items.append(terminal)
        return self._content_summary(terminal_items)

    @staticmethod
    def _canonical_content_json(value: object) -> str:
        import json

        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    @staticmethod
    def _decode_content_json(value: object) -> Mapping[str, object]:
        import json

        if not isinstance(value, str):
            raise ValueError("canonical JSON evidence is missing")
        decoded = json.loads(value)
        if not isinstance(decoded, Mapping):
            raise ValueError("canonical JSON evidence is not an object")
        if LearningCatalogReleaseService._canonical_content_json(decoded) != value:
            raise ValueError("canonical JSON evidence drift")
        return decoded

    def status(self, build_id: object) -> dict[str, Any]:
        build_id = self._identifier(build_id, "buildId")
        with self.repository.transaction() as conn:
            build = self.repository.get_build(conn, build_id=build_id)
            if build is None:
                raise ApiError("catalog_build_not_found", "课程目录构建任务不存在", 404)
            release = self.repository.get_release(
                conn, release_id=str(build["release_id"])
            )
            items = self.repository.list_build_items(conn, build_id=build_id)
            readiness = self.repository.get_build_release_readiness(
                conn,
                build_id=build_id,
            )
        return self._build_payload(
            build,
            release=release,
            items=items,
            readiness=readiness,
        )

    def create(self, data: Mapping[str, Any]) -> dict[str, Any]:
        injected = sorted(_RESTRICTED_CREATE_KEYS.intersection(data))
        if injected:
            raise ApiError(
                "invalid_catalog_create_options",
                "公开课程目录创建不接受内容阶段或备课目标参数",
                400,
            )
        request_id = self._request_id(data.get("requestId"))
        grades = self._selection(
            data.get("grades"),
            supported=SUPPORTED_GRADES,
            default=tuple(sorted(SUPPORTED_GRADES)),
            code="invalid_catalog_grades",
        )
        subjects = self._selection(
            data.get("subjects"),
            supported=SUPPORTED_SUBJECTS,
            default=("chinese", "math", "english"),
            code="invalid_catalog_subjects",
        )
        variants = self._integer(data.get("variantsPerBoundary"), default=1, maximum=5)
        allow_partial = bool(data.get("allowPartial", False))
        targets = [
            boundary.to_catalog_payload()
            for boundary in PRIMARY_SKILL_BOUNDARIES
            if boundary.grade_code in grades and boundary.subject in subjects
        ]
        if not targets:
            raise ApiError("empty_catalog_target", "课程目录构建范围为空")
        is_full = len(targets) == len(PRIMARY_SKILL_BOUNDARIES)
        if not is_full and not allow_partial:
            raise ApiError(
                "partial_catalog_requires_confirmation",
                "部分课程目录只能在明确允许 allowPartial 后构建",
                409,
            )
        title = str(data.get("title") or "Mira 小学核心课程").strip()[:255]
        target_spec = {
            "schemaVersion": "mira.learning.catalog-build-target.v1",
            "curriculumVersion": PRIMARY_CURRICULUM_VERSION,
            "grades": list(grades),
            "subjects": list(subjects),
            "variantsPerBoundary": variants,
            "allowPartial": allow_partial,
            "boundaryVersions": [str(item["boundaryVersion"]) for item in targets],
        }
        try:
            with self.repository.transaction() as conn:
                self.repository.sync_boundaries(
                    conn,
                    boundaries=[
                        boundary.to_catalog_payload()
                        for boundary in PRIMARY_SKILL_BOUNDARIES
                    ],
                    curriculum_version=PRIMARY_CURRICULUM_VERSION,
                    now=now_ms(),
                )
                build, created = self.repository.create_or_get_build(
                    conn,
                    request_id=request_id,
                    curriculum_version=PRIMARY_CURRICULUM_VERSION,
                    title=title,
                    target_spec=target_spec,
                    targets=targets,
                    variants_per_boundary=variants,
                    now=now_ms(),
                )
                release = self.repository.get_release(
                    conn,
                    release_id=str(build["release_id"]),
                    for_update=True,
                )
                items = self.repository.list_build_items(
                    conn,
                    build_id=str(build["id"]),
                    for_update=True,
                )
                readiness = self.repository.get_build_release_readiness(
                    conn,
                    build_id=str(build["id"]),
                    for_update=True,
                )
        except LearningCatalogBuildConflict as exc:
            raise ApiError("catalog_build_request_conflict", str(exc), 409) from exc
        return {
            **self._build_payload(
                build,
                release=release,
                items=items,
                readiness=readiness,
            ),
            "created": created,
        }

    def create_preparation_content_build(
        self,
        *,
        request_id: str,
        title: str,
        preparation_target: Mapping[str, object],
        target_fingerprint: str,
    ) -> dict[str, object]:
        return self._create_preparation_content_build(
            request_id=request_id,
            title=title,
            preparation_target=preparation_target,
            target_fingerprint=target_fingerprint,
            planning_authority=None,
        )

    def create_authorized_preparation_content_build(
        self,
        *,
        request_id: str,
        title: str,
        preparation_target: Mapping[str, object],
        target_fingerprint: str,
        plan_id: str,
        plan_lease_token: str,
        preparation_repository: Any,
    ) -> dict[str, object]:
        normalized_request_id = self._identifier(request_id, "requestId")
        normalized_plan_id = self._identifier(plan_id, "planId")
        normalized_lease_token = self._identifier(
            plan_lease_token,
            "planLeaseToken",
        )
        if normalized_request_id != f"grade-build:{target_fingerprint}":
            raise ApiError(
                "catalog_preparation_planning_authority_stale",
                "备课计划已失效，未创建课程目录",
                409,
            )
        return self._create_preparation_content_build(
            request_id=normalized_request_id,
            title=title,
            preparation_target=preparation_target,
            target_fingerprint=target_fingerprint,
            planning_authority=(
                preparation_repository,
                normalized_plan_id,
                normalized_lease_token,
            ),
        )

    def _create_preparation_content_build(
        self,
        *,
        request_id: str,
        title: str,
        preparation_target: Mapping[str, object],
        target_fingerprint: str,
        planning_authority: tuple[Any, str, str] | None,
    ) -> dict[str, object]:
        request_id = self._identifier(request_id, "requestId")
        normalized_title = str(title or "").strip()[:255]
        if not normalized_title:
            raise ApiError("invalid_catalog_title", "课程目录标题不能为空")
        canonical_target = canonical_preparation_target_for(preparation_target)
        canonical_json = self.repository.encode_json(canonical_target)
        provided_json = self.repository.encode_json(preparation_target)
        canonical_fingerprint = preparation_target_fingerprint(canonical_target)
        provided_fingerprint = preparation_target_fingerprint(preparation_target)
        if (
            provided_json != canonical_json
            or "allowPartial" in preparation_target
            or str(target_fingerprint or "") != canonical_fingerprint
            or provided_fingerprint != canonical_fingerprint
        ):
            raise ApiError(
                "catalog_preparation_target_conflict",
                "备课内容目标与已批准的对应年级正式合同不一致",
                409,
            )
        try:
            with self.repository.transaction() as conn:
                create_now = (
                    self._trusted_content_now()
                    if planning_authority is not None
                    else now_ms()
                )
                if planning_authority is not None:
                    preparation_repository, plan_id, plan_lease_token = (
                        planning_authority
                    )
                    authorize = getattr(
                        preparation_repository,
                        "authorize_shared_build_planning",
                        None,
                    )
                    if not callable(authorize):
                        raise ValueError(
                            "preparation planning authority is unavailable"
                        )
                    if authorize(
                        conn,
                        plan_id=plan_id,
                        plan_lease_token=plan_lease_token,
                        target_fingerprint=canonical_fingerprint,
                        now=create_now,
                    ) is not True:
                        raise ApiError(
                            "catalog_preparation_planning_authority_stale",
                            "备课计划已失效，未创建课程目录",
                            409,
                        )
                build, created = self.repository.create_or_get_content_build(
                    conn,
                    request_id=request_id,
                    curriculum_version=str(canonical_target["curriculumVersion"]),
                    title=normalized_title,
                    target_spec=canonical_target,
                    target_fingerprint=canonical_fingerprint,
                    now=create_now,
                )
                release = self.repository.get_release(
                    conn,
                    release_id=str(build["release_id"]),
                    for_update=True,
                )
                items = self.repository.list_build_items(
                    conn,
                    build_id=str(build["id"]),
                    for_update=True,
                )
                readiness = self.repository.get_build_release_readiness(
                    conn,
                    build_id=str(build["id"]),
                    for_update=True,
                )
        except LearningCatalogBuildConflict as exc:
            raise ApiError("catalog_build_request_conflict", str(exc), 409) from exc
        return {
            **self._build_payload(
                build,
                release=release,
                items=items,
                readiness=readiness,
            ),
            "created": created,
        }

    def run(self, build_id: object, data: Mapping[str, Any]) -> dict[str, Any]:
        build_id = self._identifier(build_id, "buildId")
        maximum = self._integer(data.get("maxItems"), default=1, maximum=100)
        retry_failed = bool(data.get("retryFailed", True))
        retry_external_value = data.get("retryExternal", False)
        if not isinstance(retry_external_value, bool):
            raise ApiError(
                "invalid_catalog_run_options",
                "retryExternal必须是布尔值",
            )
        retry_external = retry_external_value
        use_feedback_value = data.get("useGenerationFeedback", False)
        if not isinstance(use_feedback_value, bool):
            raise ApiError(
                "invalid_catalog_run_options",
                "useGenerationFeedback必须是布尔值",
            )
        use_generation_feedback = use_feedback_value
        processed: list[dict[str, Any]] = []
        processed_item_ids: set[str] = set()
        for _ in range(maximum):
            with self.repository.transaction() as conn:
                _release, build = self.repository.lock_build_authority(
                    conn, build_id=build_id
                )
                if build is None:
                    raise ApiError(
                        "catalog_build_not_found", "课程目录构建任务不存在", 404
                    )
                self.repository.list_build_items(
                    conn,
                    build_id=build_id,
                    for_update=True,
                )
                if (
                    str(build.get("execution_mode") or "") != "full_pipeline"
                    or str(build.get("stage_ceiling") or "") != "active_release"
                ):
                    raise ApiError(
                        "catalog_content_only_build_isolated",
                        "内容候选构建不能进入旧版课程生成或课件链路",
                        409,
                    )
                if str(build["status"]) == "completed":
                    break
                item = self.repository.claim_next_item(
                    conn,
                    build_id=build_id,
                    now=now_ms(),
                    retry_failed=retry_failed,
                    stale_before=now_ms() - 15 * 60 * 1000,
                    retry_external=retry_external,
                    excluding_item_ids=tuple(processed_item_ids),
                )
            if item is None:
                break
            processed_item_ids.add(str(item["id"]))
            processed.append(
                self._process_item(
                    item,
                    use_generation_feedback=use_generation_feedback,
                )
            )
        with self.repository.transaction() as conn:
            build = self.repository.refresh_build_counts(
                conn, build_id=build_id, now=now_ms()
            )
            release = self.repository.get_release(
                conn, release_id=str(build["release_id"])
            )
            items = self.repository.list_build_items(conn, build_id=build_id)
            readiness = self.repository.get_build_release_readiness(
                conn,
                build_id=build_id,
            )
        return {
            **self._build_payload(
                build,
                release=release,
                items=items,
                readiness=readiness,
            ),
            "processed": processed,
        }

    def activate(self, release_id: object) -> dict[str, Any]:
        release_id = self._identifier(release_id, "releaseId")
        expected = {boundary.boundary_version for boundary in PRIMARY_SKILL_BOUNDARIES}
        try:
            with self.repository.transaction() as conn:
                release = self.repository.get_release(
                    conn,
                    release_id=release_id,
                    for_update=True,
                )
                if release is None:
                    raise ApiError(
                        "catalog_release_not_found", "课程目录发布版本不存在", 404
                    )
                build = self.repository.get_build_by_release(
                    conn,
                    release_id=release_id,
                    for_update=True,
                )
                if build is None:
                    raise ApiError(
                        "catalog_build_not_found", "课程目录构建任务不存在", 404
                    )
                items = self.repository.list_build_items(
                    conn,
                    build_id=str(build["id"]),
                    for_update=True,
                )
                if (
                    str(build.get("execution_mode") or "") != "full_pipeline"
                    or str(build.get("stage_ceiling") or "") != "active_release"
                ):
                    raise ApiError(
                        "catalog_content_only_build_isolated",
                        "内容候选构建不能进入旧版激活链路",
                        409,
                    )
                spec = self.repository.decode_json(build.get("target_spec_json"))
                self._validate_release_items(conn, items=items)
                activated = self.repository.activate_release(
                    conn,
                    release_id=release_id,
                    expected_boundary_versions=expected,
                    allow_partial=bool(spec.get("allowPartial", False)),
                    now=now_ms(),
                )
        except LearningCatalogActivationError as exc:
            raise ApiError("catalog_release_not_ready", str(exc), 409) from exc
        return {
            "ok": True,
            "release": self._release_payload(activated),
        }

    def _process_item(
        self,
        item: Mapping[str, Any],
        *,
        use_generation_feedback: bool = False,
    ) -> dict[str, Any]:
        item_id = str(item["id"])
        course_id = str(item.get("course_id") or "")
        course_version = str(item.get("course_version") or "")
        stage = "course" if not course_id or not course_version else "content_gate"
        try:
            if not course_id or not course_version:
                request_id = str(item.get("active_generation_request_id") or "")
                if not request_id:
                    raise _CatalogItemError(
                        "catalog_attempt_request_missing",
                        "课程目录生成尝试缺少幂等请求标识",
                    )
                prior_error_code = str(item.get("prior_error_code") or "").strip()
                prior_error_message = str(
                    item.get("prior_error_message_safe") or ""
                ).strip()
                generation_feedback = (
                    {
                        "code": prior_error_code,
                        "message": prior_error_message,
                    }
                    if use_generation_feedback
                    and prior_error_code
                    and prior_error_message
                    else None
                )
                generated = self.dynamic_generation_service.generate_for_skill(
                    grade_code=str(item["grade_code"]),
                    subject=str(item["subject"]),
                    skill_id=str(item["skill_id"]),
                    attempts=1,
                    request_id=request_id,
                    enqueue_classroom=False,
                    generation_feedback=generation_feedback,
                    retry_transient_failed=(
                        str(item.get("claimed_from_status") or "")
                        == "external_failed"
                    ),
                )
                if not generated.payload.get("ok"):
                    raise _CatalogItemError(
                        str(generated.payload.get("error") or "course_generation_failed"),
                        str(generated.payload.get("message") or "课程生成失败"),
                    )
                course = generated.payload.get("course") or {}
                if (
                    str(course.get("curriculumVersion") or "")
                    != str(item["curriculum_version"])
                    or str(course.get("boundaryVersion") or "")
                    != str(item["boundary_version"])
                ):
                    raise _CatalogItemError(
                        "generated_boundary_version_mismatch",
                        "生成课程没有使用构建任务指定的能力边界版本",
                    )
                course_id = str(course["id"])
                course_version = str(course["version"])
                with self.repository.transaction() as conn:
                    item = self.repository.mark_course_ready_for_content_gate(
                        conn,
                        item_id=item_id,
                        course_id=course_id,
                        course_version=course_version,
                        expected_generation_request_id=request_id,
                        now=now_ms(),
                    )
                if item is None:
                    with self.repository.transaction() as conn:
                        current = self.repository.get_item(conn, item_id=item_id)
                    if current is None:
                        raise _CatalogItemError(
                            "catalog_item_not_found",
                            "课程目录项目不存在",
                        )
                    return self._item_payload(current)
                stage = "content_gate"
            self._validate_course_for_package(
                course_id=course_id,
                course_version=course_version,
            )
            if str(item.get("active_package_request_id") or ""):
                package_item = item
            else:
                with self.repository.transaction() as conn:
                    package_item = self.repository.claim_package_for_item(
                        conn,
                        item_id=item_id,
                        now=now_ms(),
                    )
                if package_item is None:
                    # Another live worker owns the processing lease.  Do not
                    # downgrade or clear its request as a package failure.
                    with self.repository.transaction() as conn:
                        current = self.repository.get_item(conn, item_id=item_id)
                    return self._item_payload(current or item)
            item = package_item
            stage = "package"
            package_request = str(item.get("active_package_request_id") or "")
            if not package_request:
                raise _CatalogItemError(
                    "catalog_package_request_missing",
                    "课件生成尝试缺少幂等请求标识",
                )
            packaged = self.lesson_package_service.generate(
                {
                    "courseId": course_id,
                    "courseVersion": course_version,
                    "requestId": package_request,
                }
            )
            package = packaged.payload.get("package") or {}
            package_status = str(
                packaged.payload.get("status") or package.get("status") or ""
            )
            if package_status == "media_pending":
                # Media generation/review is asynchronous. Keep the generated
                # course and let a later bounded run replay the idempotent
                # package request after the media worker finalizes it.
                with self.repository.transaction() as conn:
                    pending = self.repository.mark_package_media_pending(
                        conn,
                        item_id=item_id,
                        package_id=(str(package.get("id") or "") or None),
                        package_version=(
                            int(package["version"])
                            if package.get("version") is not None
                            else None
                        ),
                        expected_request_id=package_request,
                        now=now_ms(),
                    )
                return self._item_payload(pending)
            if package_status in {"pending", "generating"}:
                # The exact request is already being handled by a live worker.
                # Its stale lease, not this observer, owns any future recovery.
                with self.repository.transaction() as conn:
                    current = self.repository.get_item(conn, item_id=item_id)
                return self._item_payload(current or item)
            if not packaged.payload.get("ok"):
                raise _CatalogItemError(
                    str(packaged.payload.get("error") or "lesson_package_failed"),
                    str(packaged.payload.get("message") or "互动课件生成失败"),
                )
            with self.repository.transaction() as conn:
                ready = self.repository.mark_item_ready(
                    conn,
                    item_id=item_id,
                    package_id=str(package["id"]),
                    package_version=int(package["version"]),
                    expected_request_id=package_request,
                    now=now_ms(),
                )
            return self._item_payload(ready)
        except _CatalogCourseRejected as exc:
            with self.repository.transaction() as conn:
                rejected = self.repository.reject_course_for_item(
                    conn,
                    item_id=item_id,
                    error_code=exc.code,
                    error_message=exc.message,
                    expected_course_id=course_id,
                    expected_course_version=course_version,
                    expected_active_package_request_id=str(
                        item.get("active_package_request_id") or ""
                    ),
                    expected_updated_at=int(item.get("updated_at") or 0),
                    now=now_ms(),
                )
            return self._item_payload(rejected)
        except Exception as exc:
            code = getattr(exc, "code", "catalog_item_build_failed")
            message = getattr(exc, "message", str(exc) or "课程目录项目构建失败")
            with self.repository.transaction() as conn:
                if stage == "package":
                    failed = self.repository.mark_package_failed(
                        conn,
                        item_id=item_id,
                        error_code=str(code),
                        error_message=str(message),
                        expected_request_id=str(
                            item.get("active_package_request_id") or ""
                        ),
                        now=now_ms(),
                    )
                elif stage == "content_gate":
                    failed = self.repository.mark_content_gate_deferred(
                        conn,
                        item_id=item_id,
                        error_code=str(code),
                        error_message=str(message),
                        expected_course_id=course_id,
                        expected_course_version=course_version,
                        expected_generation_request_id=str(
                            item.get("active_generation_request_id") or ""
                        ),
                        expected_updated_at=int(item.get("updated_at") or 0),
                        now=now_ms(),
                    )
                else:
                    if is_transient_generation_failure(code, message):
                        failed = self.repository.mark_item_external_failed(
                            conn,
                            item_id=item_id,
                            error_code=str(code),
                            error_message=str(message),
                            expected_generation_request_id=str(
                                item.get("active_generation_request_id") or ""
                            ),
                            now=now_ms(),
                        )
                    else:
                        failed = self.repository.mark_item_failed(
                            conn,
                            item_id=item_id,
                            error_code=str(code),
                            error_message=str(message),
                            expected_generation_request_id=str(
                                item.get("active_generation_request_id") or ""
                            ),
                            now=now_ms(),
                        )
            return self._item_payload(failed)

    def _validate_course_for_package(
        self,
        *,
        course_id: str,
        course_version: str,
    ) -> None:
        with self.repository.transaction() as conn:
            row = self.repository.get_course_for_release_gate(
                conn,
                course_id=course_id,
                course_version=course_version,
            )
            if row is None:
                raise _CatalogCourseRejected(
                    "catalog_course_missing",
                    "课程版本不存在，不能生成课件",
                )
            content = self.repository.decode_json(row.get("content_json"))
        self._validate_stored_course_row(row, content=content)

    def _validate_release_items(self, conn, *, items: Sequence[Mapping[str, Any]]) -> None:
        for item in items:
            integrity = self.repository.get_item_release_integrity(
                conn,
                item_id=str(item["id"]),
            )
            if integrity is None:
                raise LearningCatalogActivationError(
                    "catalog release course/package binding is missing"
                )
            if (
                str(integrity.get("item_package_id") or "")
                != str(integrity.get("binding_package_id") or "")
                or int(integrity.get("item_package_version") or 0)
                != int(integrity.get("binding_package_version") or 0)
                or str(integrity.get("package_status") or "") != "published"
            ):
                raise LearningCatalogActivationError(
                    "catalog release package binding is not current"
                )
            content_json = str(integrity.get("content_json") or "")
            current_hash = hashlib.sha256(content_json.encode("utf-8")).hexdigest()
            if current_hash != str(
                integrity.get("source_course_content_hash") or ""
            ).lower():
                raise LearningCatalogActivationError(
                    "catalog release package was compiled from different course content"
                )
            content = self.repository.decode_json(content_json)
            try:
                self._validate_stored_course_row(integrity, content=content)
            except _CatalogCourseRejected as exc:
                raise LearningCatalogActivationError(exc.message) from exc

    def _validate_stored_course_row(
        self,
        row: Mapping[str, Any],
        *,
        content: object,
    ) -> None:
        if not isinstance(content, dict):
            raise _CatalogCourseRejected(
                "catalog_course_content_invalid",
                "课程内容无法通过发布前校验",
            )
        stored_course = {
            "id": str(row["id"]),
            "version": str(row["version"]),
            "gradeCode": str(row["grade_code"]),
            "subject": str(row["subject"]),
            "nodeCode": str(row["node_code"]),
            "title": str(row["title"]),
            "objective": str(row["objective"]),
            # Catalog validation describes the candidate's publishable shape;
            # DB visibility remains validated until release activation.
            "status": "published",
            "content": content,
        }
        try:
            self.catalog_validator.validate_course(stored_course)
        except ApiError as exc:
            raise _CatalogCourseRejected(
                "catalog_course_content_rejected",
                exc.message,
            ) from exc

    @staticmethod
    def _build_payload(
        build: Mapping[str, Any],
        *,
        release: Mapping[str, Any] | None,
        items: Sequence[Mapping[str, Any]],
        readiness: Mapping[str, int] | None = None,
    ) -> dict[str, Any]:
        terminal_failures = [
            item for item in items if str(item.get("status")) == "failed"
        ]
        visible_failures = [
            item
            for item in items
            if str(item.get("status")) in {"failed", "external_failed"}
        ]
        release_ready = int((readiness or {}).get("releaseReadyItemCount") or 0)
        media_pending = int((readiness or {}).get("mediaPendingItemCount") or 0)
        total = int(build.get("total_item_count") or 0)
        return {
            "ok": True,
            "schemaVersion": "mira.learning.catalog-build.v1",
            "build": {
                "id": str(build["id"]),
                "requestId": str(build["request_id"]),
                "status": str(build["status"]),
                "curriculumVersion": str(build["curriculum_version"]),
                "totalItemCount": int(build.get("total_item_count") or 0),
                "readyItemCount": int(build.get("ready_item_count") or 0),
                "failedItemCount": int(build.get("failed_item_count") or 0),
                "releaseReadyItemCount": release_ready,
                "mediaPendingItemCount": media_pending,
            },
            "release": LearningCatalogReleaseService._release_payload(release),
            "canActivate": (
                str(build.get("status")) == "completed"
                and str(build.get("execution_mode") or "") == "full_pipeline"
                and str(build.get("stage_ceiling") or "") == "active_release"
                and not terminal_failures
                and total > 0
                and release_ready == total
                and release is not None
                and str(release.get("status")) in {"draft", "active"}
            ),
            "failures": [
                LearningCatalogReleaseService._item_payload(item)
                for item in visible_failures[:20]
            ],
        }

    @staticmethod
    def _release_payload(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "id": str(row["id"]),
            "title": str(row["title"]),
            "status": str(row["status"]),
            "qualityStatus": str(row["quality_status"]),
            "curriculumVersion": str(row["curriculum_version"]),
            "requiredBoundaryCount": int(row.get("required_boundary_count") or 0),
            "readyItemCount": int(row.get("ready_item_count") or 0),
            "activatedAt": row.get("activated_at"),
        }

    @staticmethod
    def _item_payload(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "gradeCode": str(row["grade_code"]),
            "subject": str(row["subject"]),
            "skillId": str(row["skill_id"]),
            "boundaryVersion": str(row["boundary_version"]),
            "variantOrdinal": int(row.get("variant_ordinal") or 1),
            "status": str(row["status"]),
            "attemptCount": int(row.get("attempt_count") or 0),
            "packageAttemptCount": int(row.get("package_attempt_count") or 0),
            "courseId": row.get("course_id"),
            "courseVersion": row.get("course_version"),
            "packageId": row.get("package_id"),
            "packageVersion": row.get("package_version"),
            "error": row.get("error_code"),
            "message": row.get("error_message_safe"),
        }

    @staticmethod
    def _request_id(value: object) -> str:
        text = str(value or "").strip() or f"catalog_build_{uuid.uuid4().hex}"
        if not _REQUEST_ID.fullmatch(text):
            raise ApiError("invalid_catalog_request_id", "requestId 格式无效")
        return text

    @staticmethod
    def _identifier(value: object, field: str) -> str:
        text = str(value or "").strip()
        if not text or not _REQUEST_ID.fullmatch(text):
            raise ApiError("invalid_catalog_identifier", f"{field} 格式无效")
        return text

    @staticmethod
    def _selection(
        value: object,
        *,
        supported: frozenset[str],
        default: Sequence[str],
        code: str,
    ) -> tuple[str, ...]:
        if value is None:
            return tuple(default)
        if not isinstance(value, list):
            raise ApiError(code, "课程目录范围必须是数组")
        selected = tuple(dict.fromkeys(str(item or "").strip() for item in value))
        if not selected or any(item not in supported for item in selected):
            raise ApiError(code, "课程目录范围包含不支持的值")
        return selected

    @staticmethod
    def _integer(value: object, *, default: int, maximum: int) -> int:
        try:
            result = int(default if value is None else value)
        except (TypeError, ValueError) as exc:
            raise ApiError("invalid_catalog_limit", "课程目录数量参数无效") from exc
        if result < 1 or result > maximum:
            raise ApiError("invalid_catalog_limit", "课程目录数量参数超出范围")
        return result


class _CatalogItemError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class _CatalogCourseRejected(_CatalogItemError):
    pass
