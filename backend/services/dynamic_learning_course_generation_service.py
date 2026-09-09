from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
import math
from pathlib import Path
import re
import time
import uuid
from typing import Any, Callable, Literal, Mapping

from content.primary_skill_boundaries import (
    PRIMARY_CURRICULUM_VERSION,
    PRIMARY_SKILL_BOUNDARIES,
    PrimarySkillBoundary,
    boundaries_for,
)
from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from integrations.openmaic_question_adapter import (
    OpenMaicQuestionAdapter,
    OpenMaicQuestionError,
    OpenMaicQuestionPhaseAdapter,
    PreparedQuestionPhase,
    QuestionPhaseCommand,
    QuestionPhaseResult,
)
from repositories.dynamic_learning_course_repository import (
    DynamicLearningCourseRepository,
    LearningCourseCandidateConflict,
    LearningCourseGenerationRequestConflict,
    LearningCoursePublicationConflict,
    ProviderDispatchReservation,
)
from services.learning_generated_course_validator import (
    LearningGeneratedCourseValidator,
)
from services.learning_generation_failure_policy import (
    is_transient_generation_failure,
)


PROMPT_VERSION = "mira.openmaic.primary-question.v1"
SUPPORTED_SUBJECTS = frozenset({"chinese", "math", "english"})
SUPPORTED_GRADES = frozenset(f"primary_{grade}" for grade in range(1, 7))
RETRYABLE_GENERATION_ERRORS = frozenset(
    {
        "duplicate_generated_course",
        "generation_failed",
        "invalid_generation",
        "invalid_verification",
        "invalid_response",
    }
)
GENERATION_LEASE_MS = 15 * 60 * 1000
PROVIDER_REJECTION_RETRY_DELAYS_SECONDS = (0.25, 0.75)
LOGGER = logging.getLogger("mira.staged_content")


@dataclass(frozen=True)
class DynamicCourseGenerationResult:
    payload: dict[str, Any]
    status_code: int = 200


@dataclass(frozen=True)
class ContentPhaseWork:
    command: QuestionPhaseCommand
    attempt_initial_checkpoint: Mapping[str, object]
    item_lease_token: str
    attempt_started_at: int
    attempt_hard_deadline_at: int
    work_unit_deadline_at: int
    lease_expires_at: int


@dataclass(frozen=True)
class ContentPhaseAdvance:
    kind: Literal[
        "succeeded",
        "failed_safe",
        "ambiguous",
        "busy",
        "dependency_retry",
        "stale",
    ]
    result: QuestionPhaseResult | None
    replayed: bool
    process_started: bool


class StagedContentCandidateGenerator:
    """Advance one already-claimed content phase without downstream capability."""

    def __init__(
        self,
        *,
        repository: DynamicLearningCourseRepository,
        adapter: OpenMaicQuestionPhaseAdapter,
        clock_ms: Callable[[], int] = now_ms,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self._repository = repository
        self._adapter = adapter
        self._clock_ms = clock_ms
        self._sleeper = sleeper

    def canonicalize_phase(
        self, command: QuestionPhaseCommand
    ) -> PreparedQuestionPhase:
        """Expose Task-5's pure canonical request/hash authority to coordinators."""
        return self._adapter.canonicalize_phase(command)

    @property
    def required_phase_budget_ms(self) -> int:
        return self._adapter.required_phase_budget_ms

    def advance(
        self,
        work: ContentPhaseWork,
        *,
        heartbeat: Callable[[], bool],
    ) -> ContentPhaseAdvance:
        if not isinstance(work, ContentPhaseWork) or not callable(heartbeat):
            return self._advance("dependency_retry")
        try:
            prepared = self._adapter.preflight_phase(work.command)
        except (OSError, ValueError):
            return self._advance("dependency_retry")
        observed_at = self._trusted_now()
        if not self._fits_phase_budget(work, observed_at):
            return self._advance("dependency_retry")
        try:
            if heartbeat() is not True:
                return self._advance("dependency_retry")
        except Exception:
            return self._advance("dependency_retry")

        try:
            with self._repository.transaction() as conn:
                reservation = self._repository.reserve_provider_dispatch(
                    conn,
                    build_item_id=work.command.build_item_id,
                    logical_attempt=work.command.logical_attempt,
                    phase=work.command.phase,
                    phase_ordinal=work.command.phase_ordinal,
                    generation_request_id=work.command.generation_request_id,
                    item_lease_token=work.item_lease_token,
                    provider=str(prepared.provider["name"]),
                    model=str(prepared.provider["model"]),
                    profile=prepared.profile_sha256,
                    input_sha256=prepared.input_sha256,
                    attempt_started_at=work.attempt_started_at,
                    attempt_hard_deadline_at=work.attempt_hard_deadline_at,
                    work_unit_deadline_at=work.work_unit_deadline_at,
                    lease_expires_at=work.lease_expires_at,
                    attempt_initial_checkpoint=work.attempt_initial_checkpoint,
                    command_checkpoint=prepared.request["checkpoint"],
                    prepared_request=prepared.request,
                    required_budget_ms=self._adapter.required_phase_budget_ms,
                    clock_ms=self._clock_ms,
                )
        except (OSError, ValueError) as exc:
            LOGGER.warning(
                "provider dispatch reservation rejected phase=%s class=%s detail=%s",
                work.command.phase,
                type(exc).__name__,
                str(exc),
            )
            return self._advance("stale")

        if not isinstance(reservation, ProviderDispatchReservation):
            return self._advance("stale")
        if not reservation.created:
            return self._replay(prepared, work, reservation)

        after_commit = self._trusted_now()
        if not self._fits_phase_budget(work, after_commit):
            return self._complete_without_process(
                prepared,
                work,
                reservation,
                safe_error_code="phase_deadline_insufficient",
            )
        try:
            heartbeat_alive = heartbeat() is True
        except Exception:
            heartbeat_alive = False
        if not heartbeat_alive:
            return self._complete_without_process(
                prepared,
                work,
                reservation,
                safe_error_code="phase_lease_lost",
            )

        try:
            result = self._execute_phase_with_safe_retries(
                prepared,
                work,
                heartbeat=heartbeat,
            )
        except (OSError, TypeError, ValueError):
            result = self._control_result(work, "provider_outcome_unknown")
        completed_at = self._trusted_now()
        if not self._deadlines_live(work, completed_at):
            return self._advance(
                "ambiguous",
                result=self._control_result(work, "provider_outcome_unknown"),
                process_started=True,
            )
        output_sha256 = None
        if result.outcome == "succeeded":
            if not isinstance(result.checkpoint, Mapping):
                result = self._control_result(work, "provider_outcome_unknown")
            else:
                try:
                    output_sha256 = hashlib.sha256(
                        self._canonical_json(result.checkpoint).encode("utf-8")
                    ).hexdigest()
                except (TypeError, ValueError):
                    result = self._control_result(work, "provider_outcome_unknown")
        completed = self._complete_dispatch(
            work,
            reservation,
            result=result,
            output_sha256=output_sha256,
            completed_at=completed_at,
        )
        if not completed:
            return self._advance(
                "stale", result=result, process_started=True
            )
        return self._advance(
            result.outcome,
            result=result,
            process_started=True,
        )

    def _execute_phase_with_safe_retries(
        self,
        prepared: PreparedQuestionPhase,
        work: ContentPhaseWork,
        *,
        heartbeat: Callable[[], bool],
    ) -> QuestionPhaseResult:
        """Retry only a proven pre-completion Provider rejection.

        The durable dispatch remains single-owner.  A retry is allowed only
        when the sidecar proves that the rejected call has no Provider request
        identity, token usage, or billing evidence.  Ambiguous outcomes never
        enter this path.
        """
        result = self._normalize_execution_result(
            prepared,
            work,
            self._adapter.execute_phase(prepared),
        )
        for delay_seconds in PROVIDER_REJECTION_RETRY_DELAYS_SECONDS:
            if not self._is_proven_uncompleted_rejection(result):
                break
            retry_check_at = self._trusted_now()
            if not self._fits_phase_budget(work, retry_check_at):
                break
            try:
                if heartbeat() is not True:
                    break
                self._sleeper(delay_seconds)
                if heartbeat() is not True:
                    break
            except Exception:
                break
            retry_start_at = self._trusted_now()
            if not self._fits_phase_budget(work, retry_start_at):
                break
            result = self._normalize_execution_result(
                prepared,
                work,
                self._adapter.execute_phase(prepared),
            )
        return result

    @staticmethod
    def _is_proven_uncompleted_rejection(result: QuestionPhaseResult) -> bool:
        return (
            result.outcome == "failed_safe"
            and result.safe_error_code == "provider_request_rejected"
            and result.provider_request_id_hash is None
            and result.input_tokens is None
            and result.output_tokens is None
            and result.billing_evidence == "unknown"
        )

    def _replay(
        self,
        prepared,
        work: ContentPhaseWork,
        reservation: ProviderDispatchReservation,
    ) -> ContentPhaseAdvance:
        dispatch = reservation.dispatch
        status = str(dispatch.get("status") or "")
        if status in {"succeeded", "failed_safe", "ambiguous"}:
            try:
                result = self._adapter._normalize_stored_dispatch_result(
                    prepared, dispatch
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                return self._advance(
                    "ambiguous",
                    result=self._control_result(work, "provider_outcome_unknown"),
                    replayed=True,
                )
            return self._advance(status, result=result, replayed=True)
        if status != "dispatched":
            return self._advance("stale", replayed=True)
        now = self._trusted_now()
        same_owner = (
            str(dispatch.get("generation_request_id") or "")
            == work.command.generation_request_id
            and str(dispatch.get("item_lease_token") or "")
            == work.item_lease_token
        )
        dispatch_deadline = dispatch.get("attempt_hard_deadline_at")
        live = (
            same_owner
            and type(dispatch_deadline) is int
            and dispatch_deadline >= now
            and self._deadlines_live(work, now)
        )
        if live:
            return self._advance("busy", replayed=True)
        return self._advance(
            "ambiguous",
            result=self._control_result(work, "provider_outcome_unknown"),
            replayed=True,
        )

    def _complete_without_process(
        self,
        prepared,
        work: ContentPhaseWork,
        reservation: ProviderDispatchReservation,
        *,
        safe_error_code: str,
    ) -> ContentPhaseAdvance:
        completed_at = self._trusted_now()
        if not self._deadlines_live(work, completed_at):
            return self._advance(
                "ambiguous",
                result=self._control_result(work, "provider_outcome_unknown"),
            )
        result = QuestionPhaseResult(
            request_id=work.command.generation_request_id,
            phase=work.command.phase,
            phase_ordinal=work.command.phase_ordinal,
            outcome="failed_safe",
            checkpoint=None,
            provider_request_id_hash=None,
            input_tokens=None,
            output_tokens=None,
            billing_evidence="unknown",
            safe_error_code=safe_error_code,
            elapsed_ms=0.0,
        )
        completed = self._complete_dispatch(
            work,
            reservation,
            result=result,
            output_sha256=None,
            completed_at=completed_at,
        )
        return self._advance(
            "failed_safe" if completed else "stale",
            result=result,
        )

    def _complete_dispatch(
        self,
        work: ContentPhaseWork,
        reservation: ProviderDispatchReservation,
        *,
        result: QuestionPhaseResult,
        output_sha256: str | None,
        completed_at: int,
    ) -> bool:
        try:
            with self._repository.transaction() as conn:
                return bool(
                    self._repository.complete_provider_dispatch(
                        conn,
                        dispatch_id=str(reservation.dispatch["id"]),
                        build_item_id=work.command.build_item_id,
                        generation_request_id=work.command.generation_request_id,
                        item_lease_token=work.item_lease_token,
                        outcome=result.outcome,
                        checkpoint=result.checkpoint,
                        output_sha256=output_sha256,
                        provider_request_id_hash=result.provider_request_id_hash,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        billing_evidence=result.billing_evidence,
                        safe_error_code=result.safe_error_code,
                        completed_at=completed_at,
                    )
                )
        except (OSError, ValueError):
            return False

    def _fits_phase_budget(self, work: ContentPhaseWork, now: int) -> bool:
        if not self._deadlines_live(work, now):
            return False
        return min(
            work.lease_expires_at,
            work.work_unit_deadline_at,
            work.attempt_hard_deadline_at,
        ) - now >= self._adapter.required_phase_budget_ms

    @staticmethod
    def _normalize_execution_result(
        prepared,
        work: ContentPhaseWork,
        result: QuestionPhaseResult,
    ) -> QuestionPhaseResult:
        if not isinstance(result, QuestionPhaseResult):
            raise ValueError("question phase result type is invalid")
        command = work.command
        if (
            result.request_id != command.generation_request_id
            or result.phase != command.phase
            or type(result.phase_ordinal) is not int
            or result.phase_ordinal != command.phase_ordinal
        ):
            raise ValueError("question phase result identity mismatch")
        if (
            isinstance(result.elapsed_ms, bool)
            or not isinstance(result.elapsed_ms, (int, float))
            or not math.isfinite(float(result.elapsed_ms))
            or result.elapsed_ms < 0
        ):
            raise ValueError("question phase result elapsed evidence is invalid")
        request_hash = result.provider_request_id_hash
        if request_hash is not None and (
            not isinstance(request_hash, str)
            or re.fullmatch(r"[0-9a-f]{64}", request_hash) is None
        ):
            raise ValueError("question phase Provider request hash is invalid")
        for value in (result.input_tokens, result.output_tokens):
            if value is not None and (
                type(value) is not int or not 0 <= value <= 2_147_483_647
            ):
                raise ValueError("question phase usage is outside signed INTEGER")
        expected_billing = (
            "reported"
            if result.input_tokens is not None or result.output_tokens is not None
            else "unknown"
        )
        if result.billing_evidence != expected_billing:
            raise ValueError("question phase billing evidence is not derived")

        checkpoint = result.checkpoint
        if result.outcome == "succeeded":
            if result.safe_error_code is not None or not isinstance(
                checkpoint, Mapping
            ):
                raise ValueError("successful question phase result pairing is invalid")
            from integrations.openmaic_question_adapter import (
                _normalize_phase_output_checkpoint,
            )

            normalized = _normalize_phase_output_checkpoint(prepared, checkpoint)
            if StagedContentCandidateGenerator._canonical_json(
                checkpoint
            ) != StagedContentCandidateGenerator._canonical_json(normalized):
                raise ValueError("question phase result checkpoint is not canonical")
            checkpoint = normalized
        elif result.outcome in {"failed_safe", "ambiguous"}:
            if checkpoint is not None or not isinstance(result.safe_error_code, str):
                raise ValueError("failed question phase result pairing is invalid")
            failed_safe_codes = {
                "question_phase_invalid_input",
                "question_phase_contract_drift",
                "question_phase_unsupported",
                "question_phase_preflight_rejected",
                "question_phase_output_rejected",
                "question_phase_json_rejected",
                "question_phase_verification_json_rejected",
                "question_phase_verification_answers_rejected",
                "question_phase_verification_numeric_rejected",
                "question_phase_verification_review_rejected",
                "question_phase_verification_semantic_rejected",
                "question_phase_verification_checkpoint_rejected",
                "provider_unavailable",
                "provider_request_rejected",
                "provider_no_candidate",
                "provider_invalid_response",
            }
            ambiguous_codes = {
                "provider_timeout",
                "provider_connection_interrupted",
                "provider_response_lost",
                "provider_outcome_unknown",
            }
            allowed = (
                failed_safe_codes
                if result.outcome == "failed_safe"
                else ambiguous_codes
            )
            if result.safe_error_code not in allowed:
                raise ValueError("question phase result safe-code pairing is invalid")
        else:
            raise ValueError("question phase result outcome is invalid")
        return QuestionPhaseResult(
            request_id=command.generation_request_id,
            phase=command.phase,
            phase_ordinal=command.phase_ordinal,
            outcome=result.outcome,
            checkpoint=checkpoint,
            provider_request_id_hash=request_hash,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            billing_evidence=expected_billing,
            safe_error_code=result.safe_error_code,
            elapsed_ms=float(result.elapsed_ms),
        )

    @staticmethod
    def _deadlines_live(work: ContentPhaseWork, now: int) -> bool:
        if type(now) is not int or now < 0:
            return False
        evidence = (
            work.attempt_started_at,
            work.attempt_hard_deadline_at,
            work.work_unit_deadline_at,
            work.lease_expires_at,
        )
        if any(type(item) is not int or item < 0 for item in evidence):
            return False
        return work.attempt_started_at <= now <= min(evidence[1:])

    def _trusted_now(self) -> int:
        value = self._clock_ms()
        if type(value) is not int or value < 0:
            raise ValueError("trusted phase clock is invalid")
        return value

    @staticmethod
    def _canonical_json(value: Mapping[str, object]) -> str:
        return json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    @staticmethod
    def _control_result(
        work: ContentPhaseWork, safe_error_code: str
    ) -> QuestionPhaseResult:
        return QuestionPhaseResult(
            request_id=work.command.generation_request_id,
            phase=work.command.phase,
            phase_ordinal=work.command.phase_ordinal,
            outcome="ambiguous",
            checkpoint=None,
            provider_request_id_hash=None,
            input_tokens=None,
            output_tokens=None,
            billing_evidence="unknown",
            safe_error_code=safe_error_code,
            elapsed_ms=0.0,
        )

    @staticmethod
    def _advance(
        kind: Literal[
            "succeeded",
            "failed_safe",
            "ambiguous",
            "busy",
            "dependency_retry",
            "stale",
        ],
        *,
        result: QuestionPhaseResult | None = None,
        replayed: bool = False,
        process_started: bool = False,
    ) -> ContentPhaseAdvance:
        return ContentPhaseAdvance(
            kind=kind,
            result=result,
            replayed=replayed,
            process_started=process_started,
        )


class DynamicLearningCourseGenerationService:
    """Generate, independently solve, validate, and stage a course candidate."""

    def __init__(
        self,
        database_url: str | Path,
        *,
        adapter: OpenMaicQuestionAdapter | None = None,
        validator: LearningGeneratedCourseValidator | None = None,
        classroom_enqueue: Callable[..., Mapping[str, Any]] | None = None,
    ):
        database = Database(database_url)
        self.repository = DynamicLearningCourseRepository(database)
        self.adapter = adapter or OpenMaicQuestionAdapter()
        self.validator = validator or LearningGeneratedCourseValidator()
        self.classroom_enqueue = classroom_enqueue

    def status(self) -> dict[str, Any]:
        return {
            "schemaVersion": "mira.learning.dynamic-generation-status.v1",
            "generator": "openmaic",
            "adapter": self.adapter.availability(),
            "policy": {
                "grades": sorted(SUPPORTED_GRADES),
                "subjects": sorted(SUPPORTED_SUBJECTS),
                "questionCount": 5,
                "promptVersion": PROMPT_VERSION,
                "independentSolutionRequired": True,
                "automaticPublicationAfterValidation": False,
                "catalogReleaseRequired": True,
                "staticQuestionsAreGenerationAuthority": False,
            },
            "skillBoundaryCount": len(PRIMARY_SKILL_BOUNDARIES),
            "curriculumVersion": PRIMARY_CURRICULUM_VERSION,
        }

    def generate(
        self,
        data: Mapping[str, Any],
        *,
        enqueue_classroom: bool = True,
        retry_transient_failed: bool = False,
    ) -> DynamicCourseGenerationResult:
        grade_code = self._grade(data.get("gradeCode"))
        subject = self._subject(data.get("subject"))
        boundary = self._resolve_boundary(
            grade_code=grade_code,
            subject=subject,
            skill_id=self._optional_text(data.get("skillId"), 120),
        )
        request_id = self._request_id(data.get("requestId"))
        generation_feedback = self._generation_feedback(
            data.get("generationFeedback")
        )
        generation_spec = {
            "gradeCode": grade_code,
            "subject": subject,
            "skillBoundary": boundary.to_openmaic_payload(),
            "curriculumVersion": boundary.curriculum_version,
            "boundaryVersion": boundary.boundary_version,
            "questionCount": 5,
            **(
                {"generationFeedback": generation_feedback}
                if generation_feedback
                else {}
            ),
        }
        timestamp = now_ms()
        resume_candidate: Mapping[str, Any] | None = None
        try:
            with self.repository.transaction() as conn:
                job, created = self.repository.create_or_get_job(
                    conn,
                    request_id=request_id,
                    grade_code=grade_code,
                    subject=subject,
                    node_code=boundary.skill_id,
                    curriculum_version=boundary.curriculum_version,
                    boundary_version=boundary.boundary_version,
                    generator="openmaic",
                    provider=self.adapter.provider_name,
                    model=self.adapter.model_name,
                    prompt_version=PROMPT_VERSION,
                    requested_candidate_count=1,
                    generation_spec=generation_spec,
                    now=timestamp,
                )
                if created:
                    self.repository.mark_job_generating(
                        conn, job_id=str(job["id"]), now=timestamp
                    )
                else:
                    resume_candidate = next(
                        (
                            candidate
                            for candidate in self.repository.list_candidates(
                                conn, job_id=str(job["id"])
                            )
                            if str(candidate.get("status") or "") == "validated"
                        ),
                        None,
                    )
                    if resume_candidate is None:
                        recovered = None
                        if (
                            retry_transient_failed
                            and str(job.get("status") or "") == "failed"
                            and is_transient_generation_failure(
                                job.get("error_code"),
                                job.get("error_message_safe"),
                            )
                        ):
                            recovered = self.repository.reclaim_retryable_failed_job(
                                conn,
                                job_id=str(job["id"]),
                                expected_error_code=str(job.get("error_code") or ""),
                                expected_updated_at=int(job.get("updated_at") or 0),
                                now=timestamp,
                            )
                        elif str(job.get("status") or "") == "generating":
                            recovered = self.repository.reclaim_stale_generating_job(
                                conn,
                                job_id=str(job["id"]),
                                stale_before=timestamp - GENERATION_LEASE_MS,
                                now=timestamp,
                            )
                        if recovered is None:
                            return self._persisted_result(conn, job=job, replayed=True)
                        job = recovered
                if resume_candidate is None:
                    existing_question_fingerprints = sorted(
                        self.repository.existing_question_fingerprints(
                            conn,
                            grade_code=grade_code,
                            subject=subject,
                            node_code=boundary.skill_id,
                        )
                    )
                    existing_course_fingerprints = sorted(
                        self.repository.existing_content_fingerprints(
                            conn,
                            grade_code=grade_code,
                            subject=subject,
                            node_code=boundary.skill_id,
                        )
                    )
        except LearningCourseGenerationRequestConflict as exc:
            raise ApiError("learning_generation_request_conflict", str(exc), 409) from exc

        if resume_candidate is not None:
            try:
                staged, _ = self.repository.stage_candidate(
                    candidate_id=str(resume_candidate["id"]),
                    now=now_ms(),
                )
                classroom_generation = (
                    self._enqueue_classroom(staged)
                    if enqueue_classroom
                    else {"status": "catalog_managed"}
                )
                return DynamicCourseGenerationResult(
                    {
                        "ok": True,
                        "replayed": True,
                        "status": "validated",
                        "requestId": request_id,
                        "jobId": str(job["id"]),
                        "candidateId": str(resume_candidate["id"]),
                        "course": self._course_payload(staged),
                        "classroomGeneration": classroom_generation,
                    }
                )
            except (LearningCourseCandidateConflict, LearningCoursePublicationConflict) as exc:
                return self._persist_failure(
                    job_id=str(job["id"]),
                    code="learning_course_publication_conflict",
                    message=str(exc),
                )

        try:
            generated = self.adapter.generate(
                request_id=request_id,
                grade_code=grade_code,
                subject=subject,
                skill_boundary=boundary.to_openmaic_payload(),
                existing_question_fingerprints=existing_question_fingerprints,
                generation_feedback=generation_feedback,
            )
            generation_validation: dict[str, Any] = dict(generated.validation)
            independently_solved = self.adapter.verify(
                request_id=self._verification_request_id(request_id),
                grade_code=grade_code,
                subject=subject,
                skill_boundary=boundary.to_openmaic_payload(),
                candidate_course=generated.candidate_course,
            )
            validation = self.validator.validate(
                generated.candidate_course,
                grade_code=grade_code,
                subject=subject,
                skill_boundary=boundary.to_validation_payload(),
                independent_solution=independently_solved.solution,
                verification_request_id=independently_solved.request_id,
                existing_fingerprints=existing_course_fingerprints,
            )
            consistency_issues = self._consistency_repair_issues(
                validation.report,
                independently_solved.solution,
            )
            if consistency_issues:
                repaired = self.adapter.repair_consistency(
                    request_id=self._consistency_repair_request_id(request_id),
                    grade_code=grade_code,
                    subject=subject,
                    skill_boundary=boundary.to_openmaic_payload(),
                    candidate_course=generated.candidate_course,
                    review_issues=consistency_issues,
                )
                repaired_solution = self.adapter.verify(
                    request_id=self._verification_request_id(
                        f"{request_id}:consistency-repair"
                    ),
                    grade_code=grade_code,
                    subject=subject,
                    skill_boundary=boundary.to_openmaic_payload(),
                    candidate_course=repaired.candidate_course,
                )
                validation = self.validator.validate(
                    repaired.candidate_course,
                    grade_code=grade_code,
                    subject=subject,
                    skill_boundary=boundary.to_validation_payload(),
                    independent_solution=repaired_solution.solution,
                    verification_request_id=repaired_solution.request_id,
                    existing_fingerprints=existing_course_fingerprints,
                )
                generation_validation = {
                    **generation_validation,
                    "consistencyRepair": dict(repaired.validation),
                }
                generated = repaired
                independently_solved = repaired_solution
            if not validation.publishable:
                issue = (validation.report.get("issues") or [{}])[0]
                return self._persist_rejection(
                    job_id=str(job["id"]),
                    candidate_course=generated.candidate_course,
                    report=validation.report,
                    code=str(issue.get("code") or "generated_course_validation_failed"),
                    message=str(issue.get("message") or "Generated course failed validation"),
                )
            course = validation.require_publishable()
            course["id"] = self._published_course_id(
                grade_code=grade_code,
                subject=subject,
                skill_id=boundary.skill_id,
                request_id=request_id,
            )
            course["version"] = "1.0.0"
            with self.repository.transaction() as conn:
                candidate, _ = self.repository.create_or_get_candidate(
                    conn,
                    job_id=str(job["id"]),
                    ordinal=1,
                    course=course,
                    now=now_ms(),
                )
                self.repository.mark_candidate_validated(
                    conn,
                    candidate_id=str(candidate["id"]),
                    validation={
                        **validation.report,
                        "generation": generation_validation,
                        "questionFingerprints": list(
                            generated.question_fingerprints
                        ),
                        "independentSolver": independently_solved.solution.get(
                            "solver"
                        ),
                    },
                    now=now_ms(),
                )
            staged, _ = self.repository.stage_candidate(
                candidate_id=str(candidate["id"]), now=now_ms()
            )
            classroom_generation = (
                self._enqueue_classroom(staged)
                if enqueue_classroom
                else {"status": "catalog_managed"}
            )
            return DynamicCourseGenerationResult(
                {
                    "ok": True,
                    "replayed": False,
                    "status": "validated",
                    "requestId": request_id,
                    "jobId": str(job["id"]),
                    "candidateId": str(candidate["id"]),
                    "course": self._course_payload(staged),
                    "classroomGeneration": classroom_generation,
                    "validation": validation.report,
                    "generator": {
                        "name": "openmaic",
                        "provider": generated.provider,
                        "model": generated.model,
                        "generationElapsedMs": generated.elapsed_ms,
                        "verificationElapsedMs": independently_solved.elapsed_ms,
                    },
                }
            )
        except OpenMaicQuestionError as exc:
            return self._persist_failure(
                job_id=str(job["id"]), code=exc.code, message=exc.message
            )
        except (LearningCourseCandidateConflict, LearningCoursePublicationConflict) as exc:
            return self._persist_failure(
                job_id=str(job["id"]),
                code="learning_course_publication_conflict",
                message=str(exc),
            )
        except Exception as exc:
            return self._persist_failure(
                job_id=str(job["id"]),
                code="dynamic_generation_failed",
                message=str(exc),
            )

    def _enqueue_classroom(self, course: Mapping[str, Any]) -> dict[str, Any]:
        if self.classroom_enqueue is None:
            return {"status": "not_configured"}
        course_id = str(course["id"])
        course_version = str(course["version"])
        request_digest = hashlib.sha256(
            f"{course_id}@{course_version}".encode("utf-8")
        ).hexdigest()
        try:
            job = self.classroom_enqueue(
                course_id=course_id,
                course_version=course_version,
                request_id=f"classroom_{request_digest}",
            )
        except Exception:
            return {"status": "enqueue_failed"}
        return {
            "status": str(job.get("status") or "pending"),
            "requestId": str(job.get("requestId") or ""),
            "jobId": str(job.get("id") or ""),
        }

    def ensure_supply(
        self,
        *,
        grade_code: str,
        subject: str,
        target_per_skill: int = 1,
    ) -> list[DynamicCourseGenerationResult]:
        """Fill one grade/subject pool; intended for a background worker."""

        results: list[DynamicCourseGenerationResult] = []
        for boundary in boundaries_for(grade_code, subject):
            with self.repository.transaction() as conn:
                current = self.repository.count_published_dynamic_courses(
                    conn,
                    grade_code=grade_code,
                    subject=subject,
                    node_code=boundary.skill_id,
                    curriculum_version=boundary.curriculum_version,
                    boundary_version=boundary.boundary_version,
                )
            for _ in range(max(0, int(target_per_skill) - current)):
                results.append(
                    self.generate(
                        {
                            "gradeCode": grade_code,
                            "subject": subject,
                            "skillId": boundary.skill_id,
                        }
                    )
                )
        return results

    def generate_next(
        self,
        *,
        grade_code: str,
        subject: str,
        attempts: int = 3,
    ) -> DynamicCourseGenerationResult:
        """Generate the next least-supplied skill, retrying duplicate candidates."""

        candidates: list[tuple[int, int, PrimarySkillBoundary]] = []
        for sequence, boundary in enumerate(boundaries_for(grade_code, subject)):
            with self.repository.transaction() as conn:
                count = self.repository.count_published_dynamic_courses(
                    conn,
                    grade_code=grade_code,
                    subject=subject,
                    node_code=boundary.skill_id,
                    curriculum_version=boundary.curriculum_version,
                    boundary_version=boundary.boundary_version,
                )
            candidates.append((count, sequence, boundary))
        if not candidates:
            raise ApiError(
                "learning_skill_boundary_not_found",
                "当前年级科目的能力边界不存在",
                404,
            )
        candidates.sort(key=lambda item: (item[0], item[1]))
        boundary = candidates[0][2]
        return self.generate_for_skill(
            grade_code=grade_code,
            subject=subject,
            skill_id=boundary.skill_id,
            attempts=attempts,
        )

    def generate_for_skill(
        self,
        *,
        grade_code: str,
        subject: str,
        skill_id: str,
        attempts: int = 3,
        request_id: str | None = None,
        enqueue_classroom: bool = True,
        generation_feedback: Mapping[str, str] | None = None,
        retry_transient_failed: bool = False,
    ) -> DynamicCourseGenerationResult:
        """Generate a fresh course for the explicitly selected progression step."""

        last: DynamicCourseGenerationResult | None = None
        for attempt in range(max(1, int(attempts))):
            attempt_request_id = None
            if request_id:
                attempt_request_id = (
                    request_id if attempt == 0 else f"{request_id}.retry{attempt + 1}"
                )
            last = self.generate(
                {
                    "gradeCode": grade_code,
                    "subject": subject,
                    "skillId": skill_id,
                    **({"requestId": attempt_request_id} if attempt_request_id else {}),
                    **(
                        {"generationFeedback": dict(generation_feedback)}
                        if generation_feedback
                        else {}
                    ),
                },
                enqueue_classroom=enqueue_classroom,
                retry_transient_failed=(retry_transient_failed and attempt == 0),
            )
            if last.payload.get("ok"):
                return last
            if (
                last.status_code != 422
                and last.payload.get("error") not in RETRYABLE_GENERATION_ERRORS
            ):
                return last
        assert last is not None
        return last

    def _persisted_result(
        self, conn, *, job: Mapping[str, Any], replayed: bool
    ) -> DynamicCourseGenerationResult:
        candidates = self.repository.list_candidates(conn, job_id=str(job["id"]))
        course = None
        for candidate in candidates:
            if str(candidate.get("status")) == "course_validated":
                row = conn.execute(
                    """
                    SELECT * FROM learning_courses
                    WHERE id = ? AND version = ? LIMIT 1
                    """,
                    (candidate["course_id"], candidate["course_version"]),
                ).fetchone()
                if row is not None:
                    course = self._course_payload(row)
                    break
        status = str(job.get("status") or "queued")
        return DynamicCourseGenerationResult(
            {
                "ok": status == "validated",
                "replayed": replayed,
                "status": status,
                "requestId": str(job["request_id"]),
                "jobId": str(job["id"]),
                "course": course,
                "error": str(job.get("error_code") or "") or None,
                "message": str(job.get("error_message_safe") or "") or None,
            },
            200 if status == "validated" else 409 if status == "failed" else 202,
        )

    def _persist_rejection(
        self,
        *,
        job_id: str,
        candidate_course: Mapping[str, Any],
        report: Mapping[str, Any],
        code: str,
        message: str,
    ) -> DynamicCourseGenerationResult:
        try:
            with self.repository.transaction() as conn:
                candidate, _ = self.repository.create_or_get_candidate(
                    conn,
                    job_id=job_id,
                    ordinal=1,
                    course=candidate_course,
                    now=now_ms(),
                )
                self.repository.reject_candidate(
                    conn,
                    candidate_id=str(candidate["id"]),
                    error_code=code,
                    error_message=message,
                    validation=report,
                    now=now_ms(),
                )
                self.repository.mark_job_failed(
                    conn,
                    job_id=job_id,
                    error_code=code,
                    error_message=message,
                    now=now_ms(),
                )
        except Exception:
            return self._persist_failure(job_id=job_id, code=code, message=message)
        return DynamicCourseGenerationResult(
            {
                "ok": False,
                "status": "rejected",
                "jobId": job_id,
                "error": code,
                "message": DynamicLearningCourseGenerationService._safe_message(message),
                "validation": dict(report),
            },
            422,
        )

    def _persist_failure(
        self, *, job_id: str, code: str, message: str
    ) -> DynamicCourseGenerationResult:
        with self.repository.transaction() as conn:
            self.repository.mark_job_failed(
                conn,
                job_id=job_id,
                error_code=code,
                error_message=message,
                now=now_ms(),
            )
        return DynamicCourseGenerationResult(
            {
                "ok": False,
                "status": "failed",
                "jobId": job_id,
                "error": re.sub(r"[^a-z0-9_.-]", "_", code.lower())[:128],
                "message": self._safe_message(message),
            },
            503,
        )

    @staticmethod
    def _course_payload(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "version": str(row["version"]),
            "gradeCode": str(row["grade_code"]),
            "subject": str(row["subject"]),
            "skillId": str(row["node_code"]),
            "title": str(row["title"]),
            "objective": str(row["objective"]),
            "contentOrigin": str(row.get("content_origin") or ""),
            "generator": str(row.get("generator") or ""),
            "curriculumVersion": str(row.get("curriculum_version") or ""),
            "boundaryVersion": str(row.get("boundary_version") or ""),
            "qualityStatus": str(row.get("quality_status") or ""),
        }

    @staticmethod
    def _published_course_id(
        *, grade_code: str, subject: str, skill_id: str, request_id: str
    ) -> str:
        digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:16]
        skill = re.sub(r"[^a-z0-9]+", "_", skill_id.lower()).strip("_")[:64]
        return f"openmaic_{grade_code}_{subject}_{skill}_{digest}"

    @staticmethod
    def _verification_request_id(request_id: str) -> str:
        digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        return f"learning_verify_{digest[:48]}"

    @staticmethod
    def _consistency_repair_request_id(request_id: str) -> str:
        digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        return f"learning_consistency_{digest[:48]}"

    @staticmethod
    def _consistency_repair_issues(
        validation_report: Mapping[str, Any],
        independent_solution: Mapping[str, Any],
    ) -> tuple[str, ...]:
        report_issues = validation_report.get("issues")
        if (
            isinstance(report_issues, list)
            and len(report_issues) == 1
            and isinstance(report_issues[0], Mapping)
            and str(report_issues[0].get("code") or "")
            in {"generated_teaching_answer_leak", "generated_hint_answer_leak"}
        ):
            message = str(report_issues[0].get("message") or "").strip()[:300]
            return (message,) if message else ()
        if (
            isinstance(report_issues, list)
            and len(report_issues) == 1
            and isinstance(report_issues[0], Mapping)
            and str(report_issues[0].get("code") or "")
            == "invalid_generated_course"
        ):
            message = str(report_issues[0].get("message") or "").strip()[:300]
            repairable_catalog_messages = (
                "图形与位置课程包含错误或排他的图形/左右事实",
                "20以内数感课程包含超过 20 的数位表示",
                "20以内加减法必须在练习前明确教学加法和减法",
                "20以内加减法教学示例的算式结果错误",
                "20以内加减法教学示例的数值必须在 0 到 20 之间",
                "20以内加减法教学必须各含一个可复算的加法和减法示例",
            )
            if message in repairable_catalog_messages or re.fullmatch(
                r"练习题 .+ 的提示直接包含正确选项文案",
                message,
            ):
                return (message,)
        review = independent_solution.get("teachingReview")
        review_issues = review.get("issues") if isinstance(review, Mapping) else None
        if (
            not isinstance(report_issues, list)
            or len(report_issues) != 1
            or not isinstance(report_issues[0], Mapping)
            or str(report_issues[0].get("code") or "")
            != "independent_teaching_review_failed"
            or not isinstance(review, Mapping)
            or review.get("passed") is not False
            or not isinstance(review_issues, list)
        ):
            return ()
        normalized = tuple(
            str(item).strip()[:300]
            for item in review_issues
            if isinstance(item, str) and item.strip()
        )
        return normalized if 1 <= len(normalized) <= 3 else ()

    @staticmethod
    def _safe_message(message: object) -> str:
        return DynamicLearningCourseRepository.sanitize_error(message)

    @staticmethod
    def _request_id(value: object) -> str:
        text = str(value or "").strip()
        if not text:
            return f"learning_generate_{uuid.uuid4().hex}"
        if len(text) > 120 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", text):
            raise ApiError("invalid_learning_generation_request", "requestId格式不正确")
        return text

    @staticmethod
    def _grade(value: object) -> str:
        text = str(value or "").strip()
        if text not in SUPPORTED_GRADES:
            raise ApiError("invalid_learning_grade", "年级应为小学一年级至六年级")
        return text

    @staticmethod
    def _subject(value: object) -> str:
        text = str(value or "").strip()
        if text not in SUPPORTED_SUBJECTS:
            raise ApiError("invalid_learning_subject", "科目应为语文、数学或英语")
        return text

    @staticmethod
    def _optional_text(value: object, maximum: int) -> str:
        text = str(value or "").strip()
        if len(text) > maximum:
            raise ApiError("invalid_learning_generation_request", "字段长度超出限制")
        return text

    @classmethod
    def _generation_feedback(
        cls, value: object
    ) -> dict[str, str] | None:
        if value is None:
            return None
        if not isinstance(value, Mapping) or set(value) != {"code", "message"}:
            raise ApiError(
                "invalid_learning_generation_request",
                "generationFeedback结构无效",
            )
        code = cls._optional_text(value.get("code"), 128)
        message = cls._optional_text(value.get("message"), 512)
        if not code or not message or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", code):
            raise ApiError(
                "invalid_learning_generation_request",
                "generationFeedback内容无效",
            )
        return {"code": code, "message": message}

    @staticmethod
    def _resolve_boundary(
        *, grade_code: str, subject: str, skill_id: str
    ) -> PrimarySkillBoundary:
        candidates = boundaries_for(grade_code, subject)
        if skill_id:
            candidates = tuple(item for item in candidates if item.skill_id == skill_id)
        if not candidates:
            raise ApiError(
                "learning_skill_boundary_not_found", "当前年级科目的能力边界不存在", 404
            )
        return candidates[0]
