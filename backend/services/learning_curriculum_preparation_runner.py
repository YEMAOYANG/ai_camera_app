from __future__ import annotations

import json
import hashlib
import logging
import os
import re
import threading
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol

from core.config import LEARNING_CURRICULUM_PREPARATION_MIN_LEASE_SECONDS
from core.errors import ApiError
from core.security import now_ms as current_time_ms
from repositories.learning_curriculum_preparation_repository import (
    LearningCurriculumPreparationRepository,
)
from services.learning_catalog_release_service import (
    ContentAdvanceResult,
    ContentWorkUnitClaim,
)
from services.learning_curriculum_preparation_contract import (
    build_preparation_target,
    preparation_target_fingerprint,
)


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreparationStageResult:
    next_status: str
    next_stage: str
    ready_course_count: int
    failed_course_count: int
    subject_progress: Mapping[str, object]
    next_run_at: int
    catalog_build_id: str | None = None
    catalog_release_id: str | None = None
    hard_deadline_at: int | None = None
    already_persisted: bool = False
    result_kind: str | None = None


@dataclass(frozen=True)
class PreparationRunnerConfigProjection:
    runner_enabled: bool
    content_generation_enabled: bool
    grade_allowlist: tuple[str, ...]
    max_provider_subcalls_per_tick: int
    max_inflight_per_build: int
    canary_enabled: bool
    canary_auto_expand: bool
    reconciliation_enabled: bool
    grade_code: str
    target_fingerprint: str


class PreparationStageAdapter(Protocol):
    @property
    def supported_stages(self) -> frozenset[str]:
        raise NotImplementedError

    def advance(
        self,
        plan: Mapping[str, object],
        *,
        now_ms: int,
        heartbeat: Callable[[], bool],
    ) -> PreparationStageResult:
        raise NotImplementedError


class PreparationTransientError(RuntimeError):
    """A safe, explicitly retryable dependency failure."""


class PreparationDeterministicError(RuntimeError):
    """A terminal contract, validation, authorization, or programming failure."""


class LeaseHeartbeatGuard:
    def __init__(
        self,
        heartbeat: Callable[[], bool],
        *,
        interval_ms: int,
    ) -> None:
        if not callable(heartbeat) or type(interval_ms) is not int or interval_ms <= 0:
            raise ValueError("heartbeat guard configuration is invalid")
        self._heartbeat = heartbeat
        self._interval_seconds = interval_ms / 1000.0
        self._stop = threading.Event()
        self._failed = threading.Event()
        self._call_lock = threading.Lock()
        self._thread: threading.Thread | None = None

    @property
    def failed(self) -> bool:
        return self._failed.is_set()

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("heartbeat guard already started")
        self._thread = threading.Thread(
            target=self._run,
            name="learning-content-joint-heartbeat",
            daemon=True,
        )
        self._thread.start()

    def heartbeat(self) -> bool:
        if self._failed.is_set() or self._stop.is_set():
            return False
        with self._call_lock:
            if self._failed.is_set() or self._stop.is_set():
                return False
            try:
                alive = self._heartbeat() is True
            except Exception:
                alive = False
            if not alive:
                self._failed.set()
                self._stop.set()
            return alive

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join()

    def _run(self) -> None:
        if not self.heartbeat():
            return
        while not self._stop.wait(self._interval_seconds):
            if not self.heartbeat():
                return


class CheckpointSharedBuildAdapter:
    supported_stages = frozenset({"queued", "planning", "generating_content"})

    def __init__(
        self,
        catalog_service,
        *,
        repository: LearningCurriculumPreparationRepository | None = None,
        clock: Callable[[], int] = current_time_ms,
        plan_lease_ms: int = (
            LEARNING_CURRICULUM_PREPARATION_MIN_LEASE_SECONDS * 1000
        ),
        heartbeat_interval_ms: int | None = None,
    ):
        self.catalog_service = catalog_service
        self.repository = repository
        self.clock = clock
        self.plan_lease_ms = int(plan_lease_ms)
        self.heartbeat_interval_ms = int(
            heartbeat_interval_ms
            if heartbeat_interval_ms is not None
            else min(max(1, self.plan_lease_ms // 3), 15_000)
        )

    def advance(
        self,
        plan: Mapping[str, object],
        *,
        now_ms: int,
        heartbeat: Callable[[], bool],
    ) -> PreparationStageResult:
        if self.repository is None:
            raise PreparationDeterministicError(
                "shared-build repository is unavailable"
            )
        stage = str(plan.get("stage") or "")
        if stage == "planning":
            return self._advance_planning(plan, now_ms=now_ms)
        if stage == "generating_content":
            return self._advance_content(plan, now_ms=now_ms)
        raise PreparationDeterministicError("unsupported shared-build stage")

    def _advance_planning(
        self,
        plan: Mapping[str, object],
        *,
        now_ms: int,
    ) -> PreparationStageResult:
        request_id = str(plan["shared_build_request_id"])
        target = _target_spec(plan)
        subject_progress = _subject_progress(plan)
        authorize_now = int(self.clock())
        with self.repository.transaction() as conn:
            authorized = self.repository.authorize_shared_build_planning(
                conn,
                plan_id=str(plan["id"]),
                plan_lease_token=str(plan["lease_token"]),
                target_fingerprint=str(plan["target_fingerprint"]),
                now=authorize_now,
            )
        if not authorized:
            raise PreparationDeterministicError(
                "shared content build planning authority is stale"
            )
        try:
            payload = self.catalog_service.create_authorized_preparation_content_build(
                request_id=request_id,
                title=f"Mira {plan['grade_code']} 正式课程",
                preparation_target=target,
                target_fingerprint=str(plan["target_fingerprint"]),
                plan_id=str(plan["id"]),
                plan_lease_token=str(plan["lease_token"]),
                preparation_repository=self.repository,
            )
        except ApiError as exc:
            if exc.code == "catalog_preparation_planning_authority_stale":
                raise PreparationDeterministicError(
                    "shared content build planning authority is stale"
                ) from exc
            raise
        build = payload.get("build") if isinstance(payload, Mapping) else None
        release = payload.get("release") if isinstance(payload, Mapping) else None
        if not isinstance(build, Mapping) or not isinstance(release, Mapping):
            raise PreparationDeterministicError("catalog create response is incomplete")
        if str(build.get("requestId") or "") != request_id:
            raise PreparationDeterministicError("catalog create request identity mismatch")
        build_id = str(build.get("id") or "")
        release_id = str(release.get("id") or "")
        if not build_id or not release_id:
            raise PreparationDeterministicError("catalog create identity is incomplete")
        persist_now = int(self.clock())
        next_run_at = persist_now + 1_000
        with self.repository.transaction() as conn:
            persisted = self.repository.complete_shared_build_planning(
                conn,
                plan_id=str(plan["id"]),
                plan_lease_token=str(plan["lease_token"]),
                target_fingerprint=str(plan["target_fingerprint"]),
                catalog_build_id=build_id,
                catalog_release_id=release_id,
                now=persist_now,
                next_run_at=next_run_at,
            )
        if not persisted:
            raise PreparationDeterministicError(
                "shared content build planning authority is stale"
            )
        with self.repository.transaction() as conn:
            self.repository.reconcile_shared_build(
                conn,
                build_id=build_id,
                target_fingerprint=str(plan["target_fingerprint"]),
                now=persist_now,
            )
        return PreparationStageResult(
            next_status="running",
            next_stage="generating_content",
            ready_course_count=int(plan["ready_course_count"]),
            failed_course_count=int(plan["failed_course_count"]),
            subject_progress=subject_progress,
            next_run_at=next_run_at,
            catalog_build_id=build_id,
            catalog_release_id=release_id,
            hard_deadline_at=None,
            already_persisted=True,
            result_kind="progressed",
        )

    def _advance_content(
        self,
        plan: Mapping[str, object],
        *,
        now_ms: int,
    ) -> PreparationStageResult:
        build_id = str(plan.get("catalog_build_id") or "")
        release_id = str(plan.get("catalog_release_id") or "")
        if not build_id or not release_id:
            raise PreparationDeterministicError(
                "shared content build identity is incomplete"
            )
        bound_claim: ContentWorkUnitClaim | None = None
        guard: LeaseHeartbeatGuard | None = None

        def joint_heartbeat() -> bool:
            claim = bound_claim
            if claim is None:
                return False
            heartbeat_now = int(self.clock())
            with self.repository.transaction() as conn:
                return self.repository.heartbeat_bound_content_work_unit(
                    conn,
                    plan_id=str(plan["id"]),
                    plan_lease_token=str(plan["lease_token"]),
                    target_fingerprint=str(plan["target_fingerprint"]),
                    catalog_build_id=claim.build_id,
                    catalog_item_id=claim.item_id,
                    content_lease_token=claim.item_lease_token,
                    logical_attempt=claim.logical_attempt,
                    content_phase=claim.content_phase,
                    item_work_unit_deadline_at=claim.work_unit_deadline_at,
                    now=heartbeat_now,
                    plan_lease_ms=self.plan_lease_ms,
                )

        def bind_work_unit(claim: ContentWorkUnitClaim) -> bool:
            nonlocal bound_claim, guard
            if bound_claim is not None or claim.build_id != build_id:
                return False
            bind_now = int(self.clock())
            with self.repository.transaction() as conn:
                bound = self.repository.bind_content_work_unit(
                    conn,
                    plan_id=str(plan["id"]),
                    plan_lease_token=str(plan["lease_token"]),
                    target_fingerprint=str(plan["target_fingerprint"]),
                    catalog_build_id=claim.build_id,
                    catalog_item_id=claim.item_id,
                    content_lease_token=claim.item_lease_token,
                    logical_attempt=claim.logical_attempt,
                    content_phase=claim.content_phase,
                    item_work_unit_deadline_at=claim.work_unit_deadline_at,
                    now=bind_now,
                )
            if bound is None:
                return False
            bound_claim = claim
            guard = LeaseHeartbeatGuard(
                joint_heartbeat,
                interval_ms=self.heartbeat_interval_ms,
            )
            guard.start()
            return True

        def authorize_control_work() -> bool:
            authorize_now = int(self.clock())
            with self.repository.transaction() as conn:
                return self.repository.authorize_content_control_work(
                    conn,
                    plan_id=str(plan["id"]),
                    plan_lease_token=str(plan["lease_token"]),
                    target_fingerprint=str(plan["target_fingerprint"]),
                    catalog_build_id=build_id,
                    now=authorize_now,
                )

        try:
            result = self.catalog_service.advance_content(
                build_id,
                heartbeat=(
                    lambda: guard.heartbeat() if guard is not None else False
                ),
                bind_work_unit=bind_work_unit,
                authorize_control_work=authorize_control_work,
            )
        finally:
            if guard is not None:
                guard.stop()
        if not isinstance(result, ContentAdvanceResult):
            raise PreparationDeterministicError(
                "content advance result is invalid"
            )
        result_now = int(self.clock())
        reconcile_owner = {
            "owner_plan_id": str(plan["id"]),
            "owner_lease_token": str(plan["lease_token"]),
        }
        handoff_owner_complete = False
        if result.kind != "dependency_retry":
            with self.repository.transaction() as conn:
                if result.kind == "handoff":
                    reconciliation = (
                        self.repository.reconcile_shared_build_with_owner_outcome(
                            conn,
                            build_id=build_id,
                            target_fingerprint=str(plan["target_fingerprint"]),
                            now=result_now,
                            **reconcile_owner,
                        )
                    )
                    handoff_owner_complete = reconciliation.exact_owner_handoff
                else:
                    self.repository.reconcile_shared_build(
                        conn,
                        build_id=build_id,
                        target_fingerprint=str(plan["target_fingerprint"]),
                        now=result_now,
                        **reconcile_owner,
                    )
        isolated_failure = False
        if result.kind == "failed" and plan.get("library_target_fingerprint"):
            with self.repository.transaction() as conn:
                persisted = conn.execute("SELECT status, error_code FROM learning_catalog_build_jobs WHERE id = ?", (build_id,)).fetchone()
                isolated_failure = bool(persisted and persisted['status'] == 'running' and persisted['error_code'] is None)
        if result.kind == "failed" and not isolated_failure:
            with self.repository.transaction() as conn:
                self.repository.fail_shared_build_plans(
                    conn,
                    build_id=build_id,
                    target_fingerprint=str(plan["target_fingerprint"]),
                    now=result_now,
                )
            next_status = "failed"
            next_stage = "completed"
            next_run_at = result_now
        elif result.kind == "handoff":
            next_status = "running" if handoff_owner_complete else "stale"
            next_stage = (
                "building_classrooms"
                if handoff_owner_complete
                else "generating_content"
            )
            next_run_at = result_now
        elif result.kind == "dependency_retry":
            deadline = int(
                bound_claim.work_unit_deadline_at
                if bound_claim is not None
                else plan["hard_deadline_at"]
            )
            if result_now >= deadline:
                raise PreparationDeterministicError(
                    "content dependency retry exceeded its deadline"
                )
            retry_at = min(result_now + 30_000, deadline)
            with self.repository.transaction() as conn:
                deferred = self.repository.defer_bound_dependency(
                    conn,
                    plan_id=str(plan["id"]),
                    plan_lease_token=str(plan["lease_token"]),
                    target_fingerprint=str(plan["target_fingerprint"]),
                    expected_stage="generating_content",
                    next_run_at=retry_at,
                    now=result_now,
                    catalog_build_id=build_id,
                    catalog_release_id=release_id,
                    work_unit_kind=(
                        bound_claim.work_unit_kind
                        if bound_claim is not None
                        else "coordinator"
                    ),
                    bound_catalog_item_id=(
                        bound_claim.item_id
                        if bound_claim is not None
                        else None
                    ),
                    bound_content_lease_token=(
                        bound_claim.item_lease_token
                        if bound_claim is not None
                        else None
                    ),
                    bound_item_work_unit_deadline_at=(
                        bound_claim.work_unit_deadline_at
                        if bound_claim is not None
                        else None
                    ),
                    bound_logical_attempt=(
                        bound_claim.logical_attempt
                        if bound_claim is not None
                        else None
                    ),
                    bound_content_phase=(
                        bound_claim.content_phase
                        if bound_claim is not None
                        else None
                    ),
                )
            next_status = "queued" if deferred else "stale"
            next_stage = "retry_wait" if deferred else "generating_content"
            next_run_at = retry_at
        else:
            next_run_at = result_now + 1_000
            with self.repository.transaction() as conn:
                released = self.repository.release_content_continuation(
                    conn,
                    plan_id=str(plan["id"]),
                    plan_lease_token=str(plan["lease_token"]),
                    target_fingerprint=str(plan["target_fingerprint"]),
                    catalog_build_id=build_id,
                    next_run_at=next_run_at,
                    now=result_now,
                    progressed=result.kind == "progressed" or isolated_failure,
                )
            next_status = "running" if released else "stale"
            next_stage = "generating_content"
        return PreparationStageResult(
            next_status=next_status,
            next_stage=next_stage,
            ready_course_count=int(plan["ready_course_count"]),
            failed_course_count=int(plan["failed_course_count"]),
            subject_progress=_subject_progress(plan),
            next_run_at=next_run_at,
            catalog_build_id=build_id,
            catalog_release_id=release_id,
            hard_deadline_at=None,
            already_persisted=True,
            result_kind=(
                ("item_failed" if isolated_failure else result.kind)
                if result.kind != "handoff" or handoff_owner_complete
                else "stale"
            ),
        )


class FormalProductionStageAdapter(CheckpointSharedBuildAdapter):
    """Continue one formal grade build through machine publication."""

    supported_stages = frozenset({
        *CheckpointSharedBuildAdapter.supported_stages,
        "building_classrooms",
        "generating_speech",
        "validating",
        "publishing",
    })

    def __init__(
        self,
        catalog_service,
        *,
        repository: LearningCurriculumPreparationRepository,
        runtime_candidate_processor: Callable[[], object] | None,
        formal_repository,
        formal_audio_service,
        formal_audio_validation_enabled: bool = False,
        formal_auto_publication_enabled: bool = False,
        formal_provider_readiness_client=None,
        formal_route_probe_service=None,
        formal_route_probe_client=None,
        max_progressive_published_courses: int | None = None,
        clock: Callable[[], int] = current_time_ms,
        plan_lease_ms: int = (
            LEARNING_CURRICULUM_PREPARATION_MIN_LEASE_SECONDS * 1000
        ),
        heartbeat_interval_ms: int | None = None,
    ) -> None:
        super().__init__(
            catalog_service,
            repository=repository,
            clock=clock,
            plan_lease_ms=plan_lease_ms,
            heartbeat_interval_ms=heartbeat_interval_ms,
        )
        self.runtime_candidate_processor = runtime_candidate_processor
        self.formal_repository = formal_repository
        self.formal_audio_service = formal_audio_service
        self.formal_audio_validation_enabled = (
            formal_audio_validation_enabled is True
        )
        self.formal_auto_publication_enabled = (
            formal_auto_publication_enabled is True
        )
        self.formal_provider_readiness_client = formal_provider_readiness_client
        self.formal_route_probe_service = formal_route_probe_service
        self.formal_route_probe_client = formal_route_probe_client
        if max_progressive_published_courses is not None and (
            type(max_progressive_published_courses) is not int
            or max_progressive_published_courses < 1
        ):
            raise ValueError(
                "max_progressive_published_courses must be a positive integer"
            )
        self.max_progressive_published_courses = (
            max_progressive_published_courses
        )

    def advance(
        self,
        plan: Mapping[str, object],
        *,
        now_ms: int,
        heartbeat: Callable[[], bool],
    ) -> PreparationStageResult:
        stage = str(plan.get("stage") or "")
        if stage in CheckpointSharedBuildAdapter.supported_stages:
            progressive = None
            if (
                stage == "generating_content"
                and str(plan.get("work_unit_kind") or "") == "coordinator"
            ):
                guard = LeaseHeartbeatGuard(
                    heartbeat, interval_ms=self.heartbeat_interval_ms
                )
                guard.start()
                try:
                    progressive = self._process_progressive_formal_tail(
                        plan,
                        stage=stage,
                    )
                finally:
                    guard.stop()
                publication_limit = self.max_progressive_published_courses
                if (
                    publication_limit is not None
                    and progressive is not None
                    and int(progressive.get("published") or 0)
                    >= publication_limit
                ):
                    return self._pause_at_progressive_publication_limit(plan)
                publication_wait = self._pause_content_for_next_publication(
                    plan,
                    progressive=progressive,
                )
                if publication_wait is not None:
                    return publication_wait
            return super().advance(plan, now_ms=now_ms, heartbeat=heartbeat)
        if stage not in {
            "building_classrooms",
            "generating_speech",
            "validating",
            "publishing",
        }:
            raise PreparationDeterministicError("unsupported formal production stage")
        if stage == "validating":
            return self._advance_validation(plan, heartbeat=heartbeat)
        if stage == "publishing":
            return self._advance_publication(plan, heartbeat=heartbeat)
        return self._advance_formal(plan, stage=stage, heartbeat=heartbeat)

    def _advance_validation(
        self,
        plan: Mapping[str, object],
        *,
        heartbeat: Callable[[], bool],
    ) -> PreparationStageResult:
        if self.formal_provider_readiness_client is None:
            raise PreparationTransientError(
                "formal Provider readiness client is not configured"
            )
        guard = LeaseHeartbeatGuard(
            heartbeat, interval_ms=self.heartbeat_interval_ms
        )
        guard.start()
        try:
            result = self.catalog_service.advance_grade_validation(
                grade_code=str(plan["grade_code"]),
                build_id=str(plan["catalog_build_id"]),
                release_id=str(plan["catalog_release_id"]),
                target_fingerprint=str(plan["target_fingerprint"]),
                publisher_plan_id=str(plan["id"]),
                publisher_lease_token=str(plan["lease_token"]),
                preparation_repository=self.repository,
                provider_readiness_client=self.formal_provider_readiness_client,
                route_probe_service=self.formal_route_probe_service,
                route_probe_client=self.formal_route_probe_client,
            )
        finally:
            guard.stop()
        total = int(result.get("total") or 0)
        ready = int(result.get("ready") or 0)
        failed = int(result.get("failed") or 0)
        ambiguous = int(result.get("ambiguous") or 0)
        if total != 30 or failed or ambiguous or not 0 <= ready <= total:
            raise PreparationDeterministicError(
                "formal Provider readiness emitted terminal or incomplete authority"
            )
        next_stage = "publishing" if ready == total else "validating"
        return PreparationStageResult(
            next_status="running",
            next_stage=next_stage,
            ready_course_count=int(plan["ready_course_count"]),
            failed_course_count=int(plan["failed_course_count"]),
            subject_progress=_subject_progress(plan),
            next_run_at=int(self.clock()) + 1_000,
            catalog_build_id=str(plan["catalog_build_id"]),
            catalog_release_id=str(plan["catalog_release_id"]),
            hard_deadline_at=None,
            already_persisted=True,
            result_kind="progressed",
        )

    def _advance_publication(
        self,
        plan: Mapping[str, object],
        *,
        heartbeat: Callable[[], bool],
    ) -> PreparationStageResult:
        if not self.formal_auto_publication_enabled:
            raise PreparationTransientError(
                "formal automatic publication is disabled"
            )
        if not heartbeat():
            raise PreparationDeterministicError(
                "formal publication lease is stale"
            )
        grade_code = str(plan["grade_code"])
        build_id = str(plan["catalog_build_id"])
        target_fingerprint = str(plan["target_fingerprint"])
        request_digest = hashlib.sha256(
            f"{grade_code}|{build_id}|{target_fingerprint}".encode("utf-8")
        ).hexdigest()
        ready_subject_progress = _formal_ready_subject_progress(plan)
        result = self.catalog_service.activate_grade_release(
            grade_code=grade_code,
            build_id=build_id,
            target_fingerprint=target_fingerprint,
            publication_request_id=f"formal-publish:{request_digest[:48]}",
            publisher_plan_id=str(plan["id"]),
            publisher_lease_token=str(plan["lease_token"]),
            preparation_repository=self.repository,
            subject_progress=ready_subject_progress,
        )
        if (
            str(result.get("status") or "") != "ready"
            or str(result.get("stage") or "") != "completed"
            or int(result.get("completedPlanCount") or 0) < 1
        ):
            raise PreparationDeterministicError(
                "formal grade publication did not complete its preparation plans"
            )
        return PreparationStageResult(
            next_status="ready",
            next_stage="completed",
            ready_course_count=30,
            failed_course_count=0,
            subject_progress=ready_subject_progress,
            next_run_at=int(self.clock()),
            catalog_build_id=build_id,
            catalog_release_id=str(plan["catalog_release_id"]),
            hard_deadline_at=None,
            already_persisted=True,
            result_kind="published",
        )

    def _process_progressive_formal_tail(
        self,
        plan: Mapping[str, object],
        *,
        stage: str,
    ) -> dict[str, int] | None:
        """Drain ready audio/publication work before issuing another Runtime."""

        build_id = str(plan.get("catalog_build_id") or "")
        release_id = str(plan.get("catalog_release_id") or "")
        target_fingerprint = str(plan.get("target_fingerprint") or "")
        if not build_id or not release_id or not target_fingerprint:
            return None
        if plan.get("library_target_fingerprint"):
            from repositories.course_supply_repository import observe_supply_incidents
            with self.repository.transaction() as conn:
                observe_supply_incidents(conn, build_id=build_id, now=int(self.clock()))
        if self.formal_audio_validation_enabled and self.formal_audio_service is not None:
            self.formal_audio_service.process_next(
                build_id=build_id,
                release_id=release_id,
                target_fingerprint=target_fingerprint,
            )
        if not self.formal_auto_publication_enabled:
            if self.runtime_candidate_processor is not None:
                self.runtime_candidate_processor()
            return None
        result = self.catalog_service.advance_progressive_grade_validation(
            grade_code=str(plan["grade_code"]),
            build_id=build_id,
            release_id=release_id,
            target_fingerprint=target_fingerprint,
            publisher_plan_id=str(plan["id"]),
            publisher_lease_token=str(plan["lease_token"]),
            publisher_stage=stage,
            preparation_repository=self.repository,
            provider_readiness_client=self.formal_provider_readiness_client,
            route_probe_service=self.formal_route_probe_service,
            route_probe_client=self.formal_route_probe_client,
        )
        total = int(result.get("total") or 0)
        ready = int(result.get("ready") or 0)
        failed = int(result.get("failed") or 0)
        ambiguous = int(result.get("ambiguous") or 0)
        published = int(result.get("published") or 0)
        if (
            failed
            or ambiguous
            or not 0 <= ready <= total <= 30
            or not 0 <= published <= ready
        ):
            raise PreparationDeterministicError(
                "progressive formal validation emitted invalid authority"
            )
        runtime_result = None
        if self.runtime_candidate_processor is not None:
            runtime_result = self.runtime_candidate_processor()
        return {
            "blockedReason": runtime_result.get("blockedReason") if isinstance(runtime_result, Mapping) else None,
            "total": total,
            "ready": ready,
            "failed": failed,
            "ambiguous": ambiguous,
            "published": published,
        }

    def _pause_at_progressive_publication_limit(
        self,
        plan: Mapping[str, object],
    ) -> PreparationStageResult:
        """Release the coordinator before an operator-limited next course."""

        persist_now = int(self.clock())
        next_run_at = persist_now + 1_000
        with self.repository.transaction() as conn:
            released = self.repository.release_content_continuation(
                conn,
                plan_id=str(plan["id"]),
                plan_lease_token=str(plan["lease_token"]),
                target_fingerprint=str(plan["target_fingerprint"]),
                catalog_build_id=str(plan["catalog_build_id"]),
                next_run_at=next_run_at,
                now=persist_now,
                progressed=False,
            )
        return PreparationStageResult(
            next_status="running" if released else "stale",
            next_stage="generating_content",
            ready_course_count=int(plan["ready_course_count"]),
            failed_course_count=int(plan["failed_course_count"]),
            subject_progress=_subject_progress(plan),
            next_run_at=next_run_at,
            catalog_build_id=str(plan["catalog_build_id"]),
            catalog_release_id=str(plan["catalog_release_id"]),
            hard_deadline_at=None,
            already_persisted=True,
            result_kind=(
                "operator_publication_limit" if released else "stale"
            ),
        )

    def _pause_content_for_next_publication(
        self,
        plan: Mapping[str, object],
        *,
        progressive: Mapping[str, object] | None,
    ) -> PreparationStageResult | None:
        """Keep at most one unpublished course in the paid formal pipeline."""

        if progressive is None:
            return None
        counter = getattr(self.formal_repository, "formal_pipeline_counts", None)
        transaction = getattr(self.formal_repository, "transaction", None)
        if not callable(counter) or not callable(transaction):
            return None
        with transaction() as conn:
            counts = counter(
                conn,
                build_id=str(plan["catalog_build_id"]),
                release_id=str(plan["catalog_release_id"]),
                target_fingerprint=str(plan["target_fingerprint"]),
            )
        blocked_ready = 0
        incident_limit_reached = False
        if plan.get("library_target_fingerprint"):
            from repositories.course_supply_repository import observe_supply_incidents
            with self.repository.transaction() as conn:
                incidents = observe_supply_incidents(conn, build_id=str(plan["catalog_build_id"]), now=int(self.clock()))
                blocked_ready = incidents["blockedReady"]
                from services.course_library_service import POLICY_PATH
                policy = json.loads(POLICY_PATH.read_text())
                incident_limit_reached = incidents["blocked"] >= int(policy["maxOpenIncidents"])
                if int(policy["maxUnpublishedCourses"]) != 1:
                    raise PreparationDeterministicError("only one unpublished formal course is currently supported")
        elif int(counts.get("classroomFailed") or 0) or int(counts.get("speechFailed") or 0):
            raise PreparationDeterministicError(
                "formal production emitted a terminal receipt"
            )
        content_ready = int(counts.get("contentReady") or 0) - blocked_ready
        published = max(
            int(plan.get("published_course_count") or 0),
            int((progressive or {}).get("published") or 0),
        )
        blocked_reason = (progressive or {}).get("blockedReason") or ("course_supply_review_required" if incident_limit_reached else None)
        if content_ready <= published and not blocked_reason:
            return None
        persist_now = int(self.clock())
        next_run_at = persist_now + 5_000
        with self.repository.transaction() as conn:
            released = self.repository.release_content_continuation(
                conn,
                plan_id=str(plan["id"]),
                plan_lease_token=str(plan["lease_token"]),
                target_fingerprint=str(plan["target_fingerprint"]),
                catalog_build_id=str(plan["catalog_build_id"]),
                next_run_at=next_run_at,
                now=persist_now,
                progressed=False,
            )
        return PreparationStageResult(
            next_status="running" if released else "stale",
            next_stage="generating_content",
            ready_course_count=int(plan["ready_course_count"]),
            failed_course_count=int(plan["failed_course_count"]),
            subject_progress=_subject_progress(plan),
            next_run_at=next_run_at,
            catalog_build_id=str(plan["catalog_build_id"]),
            catalog_release_id=str(plan["catalog_release_id"]),
            hard_deadline_at=None,
            already_persisted=True,
            result_kind=(str(blocked_reason or "publication_wait") if released else "stale"),
        )

    def _advance_formal(
        self,
        plan: Mapping[str, object],
        *,
        stage: str,
        heartbeat: Callable[[], bool],
    ) -> PreparationStageResult:
        build_id = str(plan.get("catalog_build_id") or "")
        release_id = str(plan.get("catalog_release_id") or "")
        target_fingerprint = str(plan.get("target_fingerprint") or "")
        if not build_id or not release_id or not target_fingerprint:
            raise PreparationDeterministicError(
                "formal production identity is incomplete"
            )
        formal_repository = self.formal_repository
        if formal_repository is None:
            raise PreparationTransientError(
                "formal production repository is not configured"
            )

        def counts() -> dict[str, int]:
            with formal_repository.transaction() as conn:
                return formal_repository.formal_pipeline_counts(
                    conn,
                    build_id=build_id,
                    release_id=release_id,
                    target_fingerprint=target_fingerprint,
                )

        initial = counts()
        if initial["total"] != 30:
            raise PreparationDeterministicError(
                "formal production requires the exact thirty build items"
            )
        guard = LeaseHeartbeatGuard(
            heartbeat, interval_ms=self.heartbeat_interval_ms
        )
        guard.start()
        try:
            if initial["classroomFailed"] or initial["speechFailed"]:
                raise PreparationDeterministicError(
                    "formal production emitted a terminal receipt"
                )
            if self.runtime_candidate_processor is None:
                raise PreparationTransientError(
                    "formal Runtime generation is unavailable"
                )
            if not self.formal_audio_validation_enabled:
                raise PreparationTransientError(
                    "formal audio validation is disabled"
                )
            if self.formal_audio_service is None:
                raise PreparationTransientError(
                    "formal audio service is not configured"
                )
            self._process_progressive_formal_tail(plan, stage=stage)
            observed = counts()
            if (
                observed["total"] != 30
                or observed["classroomFailed"]
                or observed["speechFailed"]
            ):
                raise PreparationDeterministicError(
                    "formal production emitted a terminal receipt"
                )
            persisted_at = int(self.clock())
            next_run_at = persisted_at + 1_000
            with self.repository.transaction() as conn:
                persisted, next_stage = (
                    self.repository.persist_formal_stage_progress(
                        conn,
                        plan_id=str(plan["id"]),
                        lease_token=str(plan["lease_token"]),
                        target_fingerprint=target_fingerprint,
                        expected_stage=stage,
                        classroom_ready_count=observed["classroomReady"],
                        speech_ready_count=observed["speechReady"],
                        next_run_at=next_run_at,
                        now=persisted_at,
                    )
                )
        finally:
            guard.stop()
        return PreparationStageResult(
            next_status="running" if persisted else "stale",
            next_stage=next_stage if persisted else stage,
            ready_course_count=int(plan["ready_course_count"]),
            failed_course_count=int(plan["failed_course_count"]),
            subject_progress=_subject_progress(plan),
            next_run_at=next_run_at,
            catalog_build_id=build_id,
            catalog_release_id=release_id,
            hard_deadline_at=None,
            already_persisted=True,
            result_kind="progressed" if persisted else "stale",
        )


class LearningCurriculumPreparationRunner:
    TRANSIENT_API_STATUSES = frozenset({429, 502, 503, 504})
    RETRY_BACKOFF_MS = 30_000
    STAGE_DEADLINE_MS = dict(
        LearningCurriculumPreparationRepository.STAGE_DEADLINE_MS
    )
    # A single no-retry classroom can legally consume 65 minutes across ten
    # TTS/download/ASR triples.  The whole thirty-course speech stage therefore
    # needs an explicit production deadline instead of inheriting Task 12's
    # placeholder 30-minute window.
    STAGE_DEADLINE_MS.update({
        "building_classrooms": 12 * 60 * 60 * 1000,
        "generating_speech": 36 * 60 * 60 * 1000,
    })
    PUBLIC_FAILURES = dict(LearningCurriculumPreparationRepository.PUBLIC_FAILURES)

    def __init__(
        self,
        *,
        repository: LearningCurriculumPreparationRepository | None = None,
        adapter: PreparationStageAdapter | None = None,
        adapter_factory: Callable[[object], PreparationStageAdapter] | None = None,
        clock: Callable[[], int] = current_time_ms,
    ) -> None:
        self.repository = repository
        self.adapter = adapter
        self.adapter_factory = adapter_factory
        self.clock = clock
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._observation: dict[str, object] = {
            "lastRunAt": None,
            "lastResultCode": None,
            "lastStage": None,
            "lastErrorCode": None,
        }

    @property
    def thread(self) -> threading.Thread | None:
        with self._lock:
            return self._thread

    def run_once(self, app, now_ms: int) -> dict[str, object]:
        config = learning_curriculum_preparation_config_projection(app)
        if not (
            config is not None
            and config.runner_enabled
            and config.content_generation_enabled
            and not bool(app.config.get("TESTING"))
        ):
            return {"claimed": 0, "disabled": True}
        repository, adapter = self._resolve_dependencies(app)
        refresh_key = (app.config.get("DATABASE_URL"), app.config.get("LEARNING_COURSE_SUPPLY_SCOPE", "canary"))
        if app.config.get("LEARNING_COURSE_LIBRARY_ENABLED") is True and (
            getattr(self, "_library_refresh_key", None) != refresh_key
            or int(self.clock()) >= getattr(self, "_library_refresh_at", 0)
        ):
            from services.course_library_service import CourseLibraryService

            CourseLibraryService(
                app.config["DATABASE_URL"], preparation_repository=repository,
                clock=self.clock,
            ).request_scope(app.config.get("LEARNING_COURSE_SUPPLY_SCOPE", "canary"))
            self._library_refresh_key = refresh_key
            self._library_refresh_at = int(self.clock()) + 60_000
        generator = getattr(getattr(adapter, "catalog_service", None),
                            "staged_content_candidate_generator", None)
        required_budget = getattr(generator, "required_phase_budget_ms", 0)
        if isinstance(repository, LearningCurriculumPreparationRepository) and required_budget:
            with repository.transaction() as conn:
                repository.renew_undispatched_content_budget(
                    conn, grade_code=config.grade_code,
                    target_fingerprint=config.target_fingerprint,
                    now=int(now_ms), required_budget_ms=int(required_budget),
                )
        with repository.transaction() as conn:
            repository.start_next_formal_pipeline(
                conn,
                grade_code=config.grade_code,
                target_fingerprint=config.target_fingerprint,
                now=int(now_ms),
            )
        lease_ms = int(
            app.config.get(
                "LEARNING_CURRICULUM_PREPARATION_LEASE_SECONDS",
                LEARNING_CURRICULUM_PREPARATION_MIN_LEASE_SECONDS,
            )
        ) * 1000
        with repository.transaction() as conn:
            plan = repository.claim_next(
                conn,
                now=int(now_ms),
                lease_ms=lease_ms,
                supported_stages=adapter.supported_stages,
                stage_deadline_ms=self.STAGE_DEADLINE_MS,
                grade_code=config.grade_code,
                target_fingerprint=config.target_fingerprint,
            )
        if plan is None:
            return {"claimed": 0}

        deadline = int(plan["hard_deadline_at"])
        if int(now_ms) >= deadline:
            return self._fail(
                repository,
                plan,
                now_ms=int(now_ms),
                code="preparation_stage_deadline_exceeded",
            )

        def heartbeat() -> bool:
            heartbeat_now = int(self.clock())
            with repository.transaction() as conn:
                return repository.heartbeat(
                    conn,
                    plan_id=str(plan["id"]),
                    lease_token=str(plan["lease_token"]),
                    target_fingerprint=str(plan["target_fingerprint"]),
                    now=heartbeat_now,
                    lease_ms=lease_ms,
                )

        try:
            result = adapter.advance(
                plan,
                now_ms=int(now_ms),
                heartbeat=heartbeat,
            )
        except Exception as exc:
            LOGGER.exception(
                "curriculum stage failed planId=%s stage=%s class=%s",
                plan.get("id"),
                plan.get("stage"),
                type(exc).__name__,
            )
            failure_now = int(self.clock())
            if failure_now >= deadline:
                return self._fail(
                    repository,
                    plan,
                    now_ms=failure_now,
                    code="preparation_stage_deadline_exceeded",
                )
            if _is_transient(exc):
                if _is_v2_content_plan(plan):
                    return self._recover_v2_content_transient(
                        repository,
                        plan,
                        now_ms=failure_now,
                    )
                next_run_at = min(failure_now + self.RETRY_BACKOFF_MS, deadline)
                with repository.transaction() as conn:
                    deferred = repository.defer_claim(
                        conn,
                        plan_id=str(plan["id"]),
                        lease_token=str(plan["lease_token"]),
                        target_fingerprint=str(plan["target_fingerprint"]),
                        expected_stage=str(plan["stage"]),
                        next_run_at=next_run_at,
                        error_code="preparation_dependency_unavailable",
                        now=failure_now,
                    )
                return {
                    "claimed": 1,
                    "status": "retry_wait" if deferred else "stale",
                    "planId": str(plan["id"]),
                    "sharedBuildRequestId": str(plan["shared_build_request_id"]),
                    "nextRunAt": next_run_at if deferred else None,
                }
            return self._fail(
                repository,
                plan,
                now_ms=failure_now,
                code=_deterministic_error_code(exc),
            )

        if result.already_persisted:
            return {
                "claimed": 1,
                "status": result.next_status,
                "stage": result.next_stage,
                "planId": str(plan["id"]),
                "sharedBuildRequestId": str(plan["shared_build_request_id"]),
                "catalogBuildId": result.catalog_build_id,
                "catalogReleaseId": result.catalog_release_id,
                "resultCode": result.result_kind,
            }

        result_now = int(self.clock())
        if result_now >= deadline:
            return self._fail(
                repository,
                plan,
                now_ms=result_now,
                code="preparation_stage_deadline_exceeded",
            )
        try:
            result_deadline = self._result_deadline(
                plan,
                result,
                result_now=result_now,
            )
            with repository.transaction() as conn:
                applied = repository.apply_stage_result(
                    conn,
                    plan_id=str(plan["id"]),
                    lease_token=str(plan["lease_token"]),
                    target_fingerprint=str(plan["target_fingerprint"]),
                    expected_stage=str(plan["stage"]),
                    next_status=result.next_status,
                    next_stage=result.next_stage,
                    ready_course_count=int(result.ready_course_count),
                    failed_course_count=int(result.failed_course_count),
                    subject_progress=result.subject_progress,
                    next_run_at=result.next_run_at,
                    hard_deadline_at=result_deadline,
                    catalog_build_id=result.catalog_build_id,
                    catalog_release_id=result.catalog_release_id,
                    now=result_now,
                )
        except Exception as exc:
            LOGGER.exception(
                "curriculum stage persistence failed planId=%s stage=%s class=%s",
                plan.get("id"),
                plan.get("stage"),
                type(exc).__name__,
            )
            return self._fail(
                repository,
                plan,
                now_ms=result_now,
                code=_deterministic_error_code(exc),
            )
        return {
            "claimed": 1,
            "status": result.next_status if applied else "stale",
            "stage": result.next_stage if applied else str(plan["stage"]),
            "planId": str(plan["id"]),
            "sharedBuildRequestId": str(plan["shared_build_request_id"]),
            "catalogBuildId": result.catalog_build_id if applied else None,
            "catalogReleaseId": result.catalog_release_id if applied else None,
        }

    @staticmethod
    def _recover_v2_content_transient(
        repository,
        plan: Mapping[str, object],
        *,
        now_ms: int,
    ) -> dict[str, object]:
        build_id = str(plan.get("catalog_build_id") or "")
        release_id = str(plan.get("catalog_release_id") or "")
        if not build_id or not release_id:
            return {
                "claimed": 1,
                "status": "stale",
                "stage": "generating_content",
                "planId": str(plan["id"]),
                "sharedBuildRequestId": str(plan["shared_build_request_id"]),
                "resultCode": "stale",
            }
        try:
            with repository.transaction() as conn:
                repository.reconcile_shared_build(
                    conn,
                    build_id=build_id,
                    target_fingerprint=str(plan["target_fingerprint"]),
                    now=int(now_ms),
                    owner_plan_id=str(plan["id"]),
                    owner_lease_token=str(plan["lease_token"]),
                )
            next_run_at = int(now_ms) + 1_000
            with repository.transaction() as conn:
                released = repository.release_content_continuation(
                    conn,
                    plan_id=str(plan["id"]),
                    plan_lease_token=str(plan["lease_token"]),
                    target_fingerprint=str(plan["target_fingerprint"]),
                    catalog_build_id=build_id,
                    next_run_at=next_run_at,
                    now=int(now_ms),
                )
        except Exception:
            # The plan lease remains intact so a later expired-claim recovery
            # can repeat the catalog-first reconciliation. Never downgrade a
            # V2 content owner to the plan-only retry_wait path here.
            return {
                "claimed": 1,
                "status": "recovering",
                "stage": "generating_content",
                "planId": str(plan["id"]),
                "sharedBuildRequestId": str(plan["shared_build_request_id"]),
                "resultCode": "recovering",
            }
        return {
            "claimed": 1,
            "status": "running" if released else "stale",
            "stage": "generating_content",
            "planId": str(plan["id"]),
            "sharedBuildRequestId": str(plan["shared_build_request_id"]),
            "catalogBuildId": build_id,
            "catalogReleaseId": release_id,
            "resultCode": "progressed" if released else "stale",
        }

    def start(self, app) -> None:
        config = learning_curriculum_preparation_config_projection(app)
        if not (
            config is not None
            and config.runner_enabled
            and config.content_generation_enabled
            and not bool(app.config.get("TESTING"))
            and _is_reloader_process(app)
        ):
            return
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            interval = int(
                app.config.get(
                    "LEARNING_CURRICULUM_PREPARATION_INTERVAL_SECONDS", 15
                )
            )
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                args=(app, interval),
                name="learning-curriculum-preparation",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> bool:
        with self._lock:
            thread = self._thread
            if thread is None:
                return True
            self._stop.set()
        thread.join(max(0.0, float(timeout)))
        stopped = not thread.is_alive()
        if stopped:
            with self._lock:
                if self._thread is thread:
                    self._thread = None
        return stopped

    def _run(self, app, interval: int) -> None:
        try:
            while not self._stop.is_set():
                try:
                    observed_at = int(self.clock())
                    # Service-factory callbacks resolve request-scoped Flask
                    # dependencies through ``current_app``.  A background
                    # runner has no implicit application context, so scope one
                    # to this tick and release it before the interval wait.
                    with app.app_context():
                        result = self.run_once(app, now_ms=observed_at)
                    self._record_observation(
                        at=observed_at,
                        result_code=str(
                            result.get("resultCode")
                            or result.get("status")
                            or ("disabled" if result.get("disabled") else "idle")
                        ),
                        stage=(
                            str(result["stage"])
                            if result.get("stage") is not None
                            else None
                        ),
                        error_code=(
                            str(result["errorCode"])
                            if result.get("errorCode") is not None
                            else None
                        ),
                    )
                except Exception as exc:
                    observed_at = int(self.clock())
                    error_code = _deterministic_error_code(exc)
                    self._record_observation(
                        at=observed_at,
                        result_code="unexpected_exception",
                        stage=None,
                        error_code=error_code,
                    )
                    LOGGER.warning(
                        "learning preparation runner failure class=%s code=%s",
                        type(exc).__name__,
                        error_code,
                    )
                self._stop.wait(interval)
        finally:
            with self._lock:
                if self._thread is threading.current_thread():
                    self._thread = None

    def _resolve_dependencies(self, app):
        repository = self.repository
        adapter = self.adapter
        if repository is not None and adapter is not None:
            return repository, adapter
        with app.app_context():
            if adapter is None:
                if self.adapter_factory is not None:
                    adapter = self.adapter_factory(app)
                else:
                    from services.service_factory import (
                        learning_curriculum_preparation_checkpoint_adapter,
                    )

                    adapter = learning_curriculum_preparation_checkpoint_adapter()
        if adapter is None:
            raise RuntimeError("preparation stage adapter is unavailable")
        if repository is None:
            repository = getattr(adapter, "repository", None)
        if not isinstance(repository, LearningCurriculumPreparationRepository):
            raise RuntimeError("preparation execution repository is unavailable")
        return repository, adapter

    def read_only_status(
        self,
        app,
        *,
        now_ms: int,
        config_projection: PreparationRunnerConfigProjection | None = None,
    ) -> dict[str, object]:
        with self._lock:
            observation = dict(self._observation)
        repository = self.repository
        if repository is None:
            with app.app_context():
                from services.service_factory import (
                    learning_curriculum_preparation_status_repository,
                )

                repository = learning_curriculum_preparation_status_repository()
        config = config_projection or learning_curriculum_preparation_config_projection(
            app
        )
        if config is None:
            raise RuntimeError("preparation runner observation scope is invalid")
        with repository.transaction() as conn:
            counts = repository.count_runner_scope(
                conn,
                now=int(now_ms),
                supported_stages=FormalProductionStageAdapter.supported_stages,
                grade_code=config.grade_code,
                target_fingerprint=config.target_fingerprint,
            )
        return {
            "lastRunAt": observation["lastRunAt"],
            "lastResultCode": observation["lastResultCode"],
            "lastStage": observation["lastStage"],
            "lastErrorCode": observation["lastErrorCode"],
            "claimablePlanCount": int(counts["claimablePlanCount"]),
            "runningPlanCount": int(counts["runningPlanCount"]),
            "expiredLeaseCount": int(counts["expiredLeaseCount"]),
        }

    def _record_observation(
        self,
        *,
        at: int,
        result_code: str,
        stage: str | None,
        error_code: str | None,
    ) -> None:
        safe_result = _safe_observation_code(result_code, "unknown")
        safe_stage = (
            _safe_observation_code(stage, "unknown") if stage is not None else None
        )
        safe_error = (
            _safe_observation_code(error_code, "preparation_generation_failed")
            if error_code is not None
            else None
        )
        with self._lock:
            self._observation = {
                "lastRunAt": int(at),
                "lastResultCode": safe_result,
                "lastStage": safe_stage,
                "lastErrorCode": safe_error,
            }

    @classmethod
    def _result_deadline(cls, plan, result, *, result_now: int) -> int | None:
        if result.next_status == "ready":
            return None
        if result.next_stage == str(plan["stage"]):
            return int(plan["hard_deadline_at"])
        try:
            duration = cls.STAGE_DEADLINE_MS[result.next_stage]
        except KeyError as exc:
            raise PreparationDeterministicError(
                "adapter returned an unsupported preparation stage"
            ) from exc
        return int(result_now) + int(duration)

    @staticmethod
    def _fail(repository, plan, *, now_ms: int, code: str) -> dict[str, object]:
        message = LearningCurriculumPreparationRunner.PUBLIC_FAILURES[code]
        with repository.transaction() as conn:
            failed = repository.fail_claim(
                conn,
                plan_id=str(plan["id"]),
                lease_token=str(plan["lease_token"]),
                target_fingerprint=str(plan["target_fingerprint"]),
                expected_stage=str(plan["stage"]),
                error_code=code,
                error_message_safe=message,
                now=int(now_ms),
            )
        return {
            "claimed": 1,
            "status": "failed" if failed else "stale",
            "planId": str(plan["id"]),
            "sharedBuildRequestId": str(plan["shared_build_request_id"]),
            "errorCode": code if failed else None,
        }


def _subject_progress(plan: Mapping[str, object]) -> Mapping[str, object]:
    value = plan["subject_progress_json"]
    if isinstance(value, str):
        decoded = json.loads(value)
        if not isinstance(decoded, Mapping):
            raise PreparationDeterministicError("subject progress is invalid")
        return decoded
    if not isinstance(value, Mapping):
        raise PreparationDeterministicError("subject progress is invalid")
    return value


def _formal_ready_subject_progress(
    plan: Mapping[str, object],
) -> Mapping[str, object]:
    progress = _subject_progress(plan)
    ready: dict[str, object] = {}
    for subject, raw_item in progress.items():
        if not isinstance(raw_item, Mapping):
            raise PreparationDeterministicError(
                "formal subject progress is invalid"
            )
        item = dict(raw_item)
        total = item.get("totalCourseCount")
        if isinstance(total, bool) or not isinstance(total, int) or total < 1:
            raise PreparationDeterministicError(
                "formal subject progress total is invalid"
            )
        item["readyCourseCount"] = total
        item["failedCourseCount"] = 0
        ready[str(subject)] = item
    return ready


def _target_spec(plan: Mapping[str, object]) -> Mapping[str, object]:
    value = plan.get("target_spec_json")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise PreparationDeterministicError(
                "preparation target is invalid"
            ) from exc
    if not isinstance(value, Mapping):
        raise PreparationDeterministicError("preparation target is invalid")
    return dict(value)


def _is_v2_content_plan(plan: Mapping[str, object]) -> bool:
    try:
        target = _target_spec(plan)
    except PreparationDeterministicError:
        return False
    return bool(
        str(target.get("schemaVersion") or "")
        == "mira.learning.preparation-target.v2"
        and str(plan.get("stage") or "") == "generating_content"
    )


def _safe_observation_code(value: object, fallback: str) -> str:
    text = str(value or fallback)
    return text if re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", text) else fallback


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, PreparationTransientError):
        return True
    if isinstance(exc, ApiError):
        return exc.status_code in LearningCurriculumPreparationRunner.TRANSIENT_API_STATUSES
    return isinstance(exc, (TimeoutError, ConnectionResetError))


def _deterministic_error_code(exc: Exception) -> str:
    if isinstance(exc, ApiError) and exc.status_code == 409:
        return "preparation_catalog_conflict"
    if isinstance(exc, (PreparationDeterministicError, ValueError, AssertionError)):
        return "preparation_validation_failed"
    return "preparation_generation_failed"


def learning_curriculum_preparation_config_projection(
    app,
) -> PreparationRunnerConfigProjection | None:
    runner_enabled = app.config.get(
        "LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED",
        False,
    )
    content_generation_enabled = app.config.get(
        "LEARNING_CURRICULUM_PREPARATION_CONTENT_GENERATION_ENABLED",
        False,
    )
    allowlist = app.config.get(
        "LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST",
        ["primary_1"],
    )
    max_provider_subcalls_per_tick = app.config.get(
        "LEARNING_CURRICULUM_PREPARATION_MAX_PROVIDER_SUBCALLS_PER_TICK",
        1,
    )
    max_inflight_per_build = app.config.get(
        "LEARNING_CURRICULUM_PREPARATION_MAX_INFLIGHT_PER_BUILD",
        1,
    )
    canary_enabled = app.config.get(
        "LEARNING_CURRICULUM_PREPARATION_CANARY_ENABLED",
        True,
    )
    canary_auto_expand = app.config.get(
        "LEARNING_CURRICULUM_PREPARATION_CANARY_AUTO_EXPAND",
        True,
    )
    reconciliation_enabled = app.config.get(
        "LEARNING_CURRICULUM_PREPARATION_RECONCILIATION_ENABLED",
        False,
    )
    if not (
        type(runner_enabled) is bool
        and type(content_generation_enabled) is bool
        and type(allowlist) is list
        and allowlist == ["primary_1"]
        and type(max_provider_subcalls_per_tick) is int
        and max_provider_subcalls_per_tick == 1
        and type(max_inflight_per_build) is int
        and max_inflight_per_build == 1
        and canary_enabled is True
        and canary_auto_expand is True
        and reconciliation_enabled is False
    ):
        return None
    grade_code = "primary_1"
    return PreparationRunnerConfigProjection(
        runner_enabled=runner_enabled,
        content_generation_enabled=content_generation_enabled,
        grade_allowlist=(grade_code,),
        max_provider_subcalls_per_tick=max_provider_subcalls_per_tick,
        max_inflight_per_build=max_inflight_per_build,
        canary_enabled=canary_enabled,
        canary_auto_expand=canary_auto_expand,
        reconciliation_enabled=reconciliation_enabled,
        grade_code=grade_code,
        target_fingerprint=preparation_target_fingerprint(
            build_preparation_target(grade_code)
        ),
    )


def _is_reloader_process(app) -> bool:
    if not bool(app.config.get("DEBUG")):
        return True
    return os.environ.get("WERKZEUG_RUN_MAIN", "").lower() == "true"


learning_curriculum_preparation_runner = LearningCurriculumPreparationRunner()


def start_learning_curriculum_preparation(app) -> None:
    learning_curriculum_preparation_runner.start(app)
