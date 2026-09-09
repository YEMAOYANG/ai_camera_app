from __future__ import annotations

import copy
from contextlib import contextmanager
import json
import os
import unittest
from unittest.mock import patch

from flask import Flask, current_app, has_app_context

from core.errors import ApiError
from services.learning_curriculum_preparation_runner import (
    CheckpointSharedBuildAdapter,
    LearningCurriculumPreparationRunner,
    PreparationStageResult,
    PreparationTransientError,
)
from services.learning_catalog_release_service import ContentAdvanceResult


class SimulatedProcessCrash(BaseException):
    pass


def _subject_progress(ready: int = 0) -> dict[str, dict[str, int]]:
    remaining = ready
    result = {}
    for subject, total in (("chinese", 12), ("math", 9), ("english", 9)):
        count = min(total, remaining)
        remaining -= count
        result[subject] = {
            "totalCourseCount": total,
            "readyCourseCount": count,
            "failedCourseCount": 0,
        }
    return result


def _app(**overrides) -> Flask:
    app = Flask(__name__)
    app.config.update(
        TESTING=False,
        DEBUG=False,
        LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED=True,
        LEARNING_CURRICULUM_PREPARATION_CONTENT_GENERATION_ENABLED=True,
        LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST=["primary_1"],
        LEARNING_CURRICULUM_PREPARATION_INTERVAL_SECONDS=5,
        LEARNING_CURRICULUM_PREPARATION_LEASE_SECONDS=90,
    )
    app.config.update(overrides)
    return app


class _FakeRepository:
    def __init__(self):
        self.plan = {
            "id": "prep_1",
            "status": "queued",
            "stage": "queued",
            "target_fingerprint": "f" * 64,
            "shared_build_request_id": "grade-build:" + "f" * 64,
            "grade_code": "primary_1",
            "target_spec_json": {
                "schemaVersion": "mira.learning.preparation-target.v2"
            },
            "ready_course_count": 0,
            "failed_course_count": 0,
            "subject_progress_json": _subject_progress(),
            "catalog_build_id": None,
            "catalog_release_id": None,
            "lease_token": None,
            "lease_expires_at": None,
            "heartbeat_at": None,
            "next_run_at": 1_000,
            "hard_deadline_at": None,
            "resume_stage": None,
            "work_unit_kind": None,
        }
        self.in_transaction = False
        self.transaction_count = 0
        self.claim_calls = 0
        self.last_claim_lease_ms = None
        self.events: list[dict[str, object]] = []
        self.crash_before_apply = False
        self.replace_token_before_apply = False

    @contextmanager
    def transaction(self):
        if self.in_transaction:
            raise AssertionError("nested fake transaction")
        self.in_transaction = True
        self.transaction_count += 1
        try:
            yield object()
        finally:
            self.in_transaction = False

    def start_next_formal_pipeline(
        self,
        _conn,
        *,
        grade_code,
        target_fingerprint,
        now,
    ):
        self.formal_pipeline_scope = (grade_code, target_fingerprint, now)
        return None

    def claim_next(
        self,
        _conn,
        *,
        now,
        lease_ms,
        supported_stages,
        stage_deadline_ms,
        grade_code,
        target_fingerprint,
    ):
        self.claim_calls += 1
        self.last_claim_lease_ms = lease_ms
        self.claim_scope = (grade_code, target_fingerprint)
        plan = self.plan
        if plan["status"] not in {"queued", "running"}:
            return None
        if plan["next_run_at"] is None or plan["next_run_at"] > now:
            return None
        if plan["lease_expires_at"] is not None and plan["lease_expires_at"] > now:
            return None
        persisted_stage = plan["stage"]
        if persisted_stage == "queued":
            if "queued" not in supported_stages:
                return None
            effective_stage = "planning"
        elif persisted_stage == "retry_wait":
            effective_stage = plan["resume_stage"]
            if effective_stage not in supported_stages:
                return None
        else:
            effective_stage = persisted_stage
            if effective_stage not in supported_stages:
                return None
        plan.update(
            status="running",
            stage=effective_stage,
            resume_stage=None,
            lease_token=f"lease-{self.claim_calls}",
            lease_expires_at=now + lease_ms,
            heartbeat_at=now,
        )
        if plan["hard_deadline_at"] is None:
            plan["hard_deadline_at"] = now + stage_deadline_ms[effective_stage]
        return copy.deepcopy(plan)

    def heartbeat(
        self,
        _conn,
        *,
        plan_id,
        lease_token,
        target_fingerprint,
        now,
        lease_ms,
    ):
        if not self._matches(plan_id, lease_token, target_fingerprint, now):
            return False
        self.plan["heartbeat_at"] = now
        self.plan["lease_expires_at"] = now + lease_ms
        return True

    def apply_stage_result(self, _conn, **kwargs):
        if self.crash_before_apply:
            self.crash_before_apply = False
            raise SimulatedProcessCrash()
        if self.replace_token_before_apply:
            self.replace_token_before_apply = False
            self.plan["lease_token"] = "newer-token"
        if not self._matches(
            kwargs["plan_id"],
            kwargs["lease_token"],
            kwargs["target_fingerprint"],
            kwargs["now"],
        ):
            return False
        if self.plan["stage"] != kwargs["expected_stage"]:
            return False
        next_status = kwargs["next_status"]
        next_stage = kwargs["next_stage"]
        self.plan.update(
            ready_course_count=kwargs["ready_course_count"],
            failed_course_count=kwargs["failed_course_count"],
            subject_progress_json=copy.deepcopy(kwargs["subject_progress"]),
            catalog_build_id=kwargs["catalog_build_id"],
            catalog_release_id=kwargs["catalog_release_id"],
        )
        if next_status == "ready":
            self.plan.update(
                status="ready",
                stage="completed",
                lease_token=None,
                lease_expires_at=None,
                heartbeat_at=None,
                next_run_at=None,
                hard_deadline_at=None,
                resume_stage=None,
            )
        elif next_status == "running":
            self.plan.update(stage=next_stage, next_run_at=kwargs["next_run_at"])
        else:
            self.plan.update(
                status="queued",
                stage="retry_wait",
                resume_stage=next_stage,
                lease_token=None,
                lease_expires_at=None,
                heartbeat_at=None,
                next_run_at=kwargs["next_run_at"],
                hard_deadline_at=kwargs["hard_deadline_at"],
            )
        self.events.append({"type": "stage_result", "stage": next_stage})
        return True

    def complete_shared_build_planning(self, _conn, **kwargs):
        if self.crash_before_apply:
            self.crash_before_apply = False
            raise SimulatedProcessCrash()
        if self.replace_token_before_apply:
            self.replace_token_before_apply = False
            self.plan["lease_token"] = "newer-token"
        if not self._matches(
            kwargs["plan_id"],
            kwargs["plan_lease_token"],
            kwargs["target_fingerprint"],
            kwargs["now"],
        ):
            return False
        self.plan.update(
            status="running",
            stage="generating_content",
            catalog_build_id=kwargs["catalog_build_id"],
            catalog_release_id=kwargs["catalog_release_id"],
            lease_token=None,
            lease_expires_at=None,
            heartbeat_at=None,
            next_run_at=kwargs["next_run_at"],
            hard_deadline_at=None,
            work_unit_kind=None,
        )
        return True

    def authorize_shared_build_planning(self, _conn, **kwargs):
        return self._matches(
            kwargs["plan_id"],
            kwargs["plan_lease_token"],
            kwargs["target_fingerprint"],
            kwargs["now"],
        )

    def reconcile_shared_build(self, _conn, **kwargs):
        return 1

    def fail_shared_build_plans(self, _conn, **kwargs):
        self.plan.update(
            status="failed",
            stage="completed",
            lease_token=None,
            lease_expires_at=None,
            hard_deadline_at=None,
            next_run_at=None,
        )
        return 1

    def defer_bound_dependency(self, _conn, **kwargs):
        if not self._matches(
            kwargs["plan_id"],
            kwargs["plan_lease_token"],
            kwargs["target_fingerprint"],
            kwargs["now"],
        ):
            return False
        self.plan.update(
            status="queued",
            stage="retry_wait",
            resume_stage=kwargs["expected_stage"],
            lease_token=None,
            lease_expires_at=None,
            heartbeat_at=None,
            next_run_at=kwargs["next_run_at"],
        )
        return True

    def release_content_continuation(self, _conn, **kwargs):
        if not self._matches(
            kwargs["plan_id"],
            kwargs["plan_lease_token"],
            kwargs["target_fingerprint"],
            kwargs["now"],
        ):
            return False
        self.plan.update(
            status="running",
            stage="generating_content",
            lease_token=None,
            lease_expires_at=None,
            heartbeat_at=None,
            next_run_at=kwargs["next_run_at"],
            hard_deadline_at=None,
        )
        return True

    def defer_claim(self, _conn, **kwargs):
        if not self._matches(
            kwargs["plan_id"],
            kwargs["lease_token"],
            kwargs["target_fingerprint"],
            kwargs["now"],
        ):
            return False
        self.plan.update(
            status="queued",
            stage="retry_wait",
            resume_stage=kwargs["expected_stage"],
            lease_token=None,
            lease_expires_at=None,
            heartbeat_at=None,
            next_run_at=kwargs["next_run_at"],
        )
        self.events.append({"type": "deferred", "stage": kwargs["expected_stage"]})
        return True

    def fail_claim(self, _conn, **kwargs):
        if not (
            self.plan["id"] == kwargs["plan_id"]
            and self.plan["lease_token"] == kwargs["lease_token"]
            and self.plan["target_fingerprint"] == kwargs["target_fingerprint"]
            and self.plan["stage"] == kwargs["expected_stage"]
        ):
            return False
        self.plan.update(
            status="failed",
            stage="completed",
            error_code=kwargs["error_code"],
            error_message_safe=kwargs["error_message_safe"],
            lease_token=None,
            lease_expires_at=None,
            heartbeat_at=None,
            next_run_at=None,
            hard_deadline_at=None,
            resume_stage=None,
            ready_course_count=self.plan["ready_course_count"],
            failed_course_count=self.plan["failed_course_count"],
            subject_progress_json=_subject_progress(
                self.plan["ready_course_count"]
            ),
        )
        self.events.append({"type": "failed", "stage": "completed"})
        return True

    def expire_lease(self, *, now_ms):
        self.plan["lease_expires_at"] = now_ms

    def _matches(self, plan_id, lease_token, target_fingerprint, now):
        return (
            self.plan["id"] == plan_id
            and self.plan["lease_token"] == lease_token
            and self.plan["target_fingerprint"] == target_fingerprint
            and self.plan["lease_expires_at"] >= now
        )


class _FakeCatalog:
    def __init__(self, failures=None):
        self.create_calls = []
        self.authorized_create_calls = []
        self.run_calls = []
        self.activate_calls = []
        self.failures = list(failures or [])

    def create(self, payload):
        raise AssertionError("checkpoint flow used public catalog create")

    def create_preparation_content_build(
        self, *, request_id, title, preparation_target, target_fingerprint
    ):
        payload = {
            "requestId": request_id,
            "title": title,
            "grades": ["primary_1"],
            "subjects": ["chinese", "math", "english"],
            "variantsPerBoundary": 3,
            "preparationTarget": copy.deepcopy(preparation_target),
            "targetFingerprint": target_fingerprint,
        }
        self.create_calls.append(copy.deepcopy(payload))
        if self.failures:
            raise self.failures.pop(0)
        return {
            "ok": True,
            "build": {"id": "catalog_build_shared", "requestId": request_id},
            "release": {"id": "catalog_release_shared"},
        }

    def create_authorized_preparation_content_build(
        self,
        *,
        request_id,
        title,
        preparation_target,
        target_fingerprint,
        plan_id,
        plan_lease_token,
        preparation_repository,
    ):
        self.authorized_create_calls.append(
            {
                "planId": plan_id,
                "planLeaseToken": plan_lease_token,
                "preparationRepository": preparation_repository,
            }
        )
        return self.create_preparation_content_build(
            request_id=request_id,
            title=title,
            preparation_target=preparation_target,
            target_fingerprint=target_fingerprint,
        )

    def advance_content(self, build_id, **kwargs):
        return ContentAdvanceResult(
            kind="busy",
            build_id=build_id,
            item_id=None,
            content_summary={},
        )

    def run(self, *args, **kwargs):
        self.run_calls.append((args, kwargs))

    def activate(self, *args, **kwargs):
        self.activate_calls.append((args, kwargs))


class _Clock:
    def __init__(self, *values):
        self.values = list(values)

    def __call__(self):
        if len(self.values) > 1:
            return self.values.pop(0)
        return self.values[0]


class _FakeProgressAdapter:
    supported_stages = frozenset(
        {
            "queued",
            "planning",
            "generating_content",
            "building_classrooms",
            "generating_speech",
            "validating",
            "publishing",
        }
    )
    order = (
        "planning",
        "generating_content",
        "building_classrooms",
        "generating_speech",
        "validating",
        "publishing",
        "ready",
    )

    def __init__(self, repository):
        self.repository = repository
        self.calls = []
        self.provider = _ForbiddenProvider()

    def advance(self, plan, *, now_ms, heartbeat):
        self.calls.append(plan["stage"])
        self.assert_transaction_closed()
        self.assertTrue_heartbeat(heartbeat())
        index = self.order.index(plan["stage"])
        next_stage = self.order[index + 1]
        ready = 30 if next_stage == "ready" else min((index + 1) * 5, 25)
        return PreparationStageResult(
            next_status="ready" if next_stage == "ready" else "queued",
            next_stage="completed" if next_stage == "ready" else next_stage,
            ready_course_count=ready,
            failed_course_count=0,
            subject_progress=_subject_progress(ready),
            next_run_at=now_ms,
        )

    def assert_transaction_closed(self):
        if self.repository.in_transaction:
            raise AssertionError("adapter ran inside claim transaction")

    @staticmethod
    def assertTrue_heartbeat(value):
        if value is not True:
            raise AssertionError("heartbeat failed")


class _ForbiddenProvider:
    def __init__(self):
        self.call_count = 0

    def generate(self):
        self.call_count += 1
        raise AssertionError("provider must not be called")


class LearningCurriculumPreparationRunnerTest(unittest.TestCase):
    def test_stage_transition_keeps_production_classroom_and_audio_deadlines(self):
        plan = {"stage": "generating_content", "hard_deadline_at": 600_000}
        for stage, hours in (("building_classrooms", 12), ("generating_speech", 36)):
            with self.subTest(stage=stage):
                result = PreparationStageResult(next_status="running", next_stage=stage,
                    ready_course_count=0, failed_course_count=0, subject_progress={}, next_run_at=1000)
                self.assertEqual(LearningCurriculumPreparationRunner._result_deadline(plan, result, result_now=1000),
                                 1000 + hours * 60 * 60 * 1000)
                same_stage = {"stage": stage, "hard_deadline_at": 123_456}
                self.assertEqual(LearningCurriculumPreparationRunner._result_deadline(same_stage, result, result_now=1000),
                                 123_456)

    def _checkpoint_runner(self, repository, catalog, **kwargs):
        adapter_clock = kwargs.get("clock", lambda: 1_001)
        return LearningCurriculumPreparationRunner(
            repository=repository,
            adapter=CheckpointSharedBuildAdapter(
                catalog,
                repository=repository,
                clock=adapter_clock,
                plan_lease_ms=90_000,
            ),
            **kwargs,
        )

    def test_run_once_reserves_shared_build_without_running_generation(self):
        repository = _FakeRepository()
        catalog = _FakeCatalog()
        runner = self._checkpoint_runner(repository, catalog, clock=_Clock(1_001))

        result = runner.run_once(_app(), now_ms=1_000)

        self.assertEqual(result["claimed"], 1)
        self.assertEqual(catalog.create_calls[0]["variantsPerBoundary"], 3)
        self.assertEqual(catalog.create_calls[0]["grades"], ["primary_1"])
        self.assertEqual(
            catalog.create_calls[0]["subjects"], ["chinese", "math", "english"]
        )
        self.assertEqual(catalog.run_calls, [])
        self.assertEqual(catalog.activate_calls, [])
        self.assertEqual(result["stage"], "generating_content")
        self.assertEqual(repository.plan["stage"], "generating_content")
        self.assertEqual(repository.plan["next_run_at"], 2_001)
        self.assertIsNone(repository.plan["hard_deadline_at"])
        self.assertIsNone(repository.plan["lease_token"])
        self.assertEqual(repository.plan["catalog_build_id"], "catalog_build_shared")

    def test_v94_default_claim_and_adapter_lease_are_at_least_360_seconds(self):
        repository = _FakeRepository()
        catalog = _FakeCatalog()
        adapter = CheckpointSharedBuildAdapter(
            catalog,
            repository=repository,
        )
        self.assertEqual(adapter.plan_lease_ms, 360_000)
        runner = LearningCurriculumPreparationRunner(
            repository=repository,
            adapter=adapter,
            clock=_Clock(1_001),
        )
        app = _app()
        app.config.pop("LEARNING_CURRICULUM_PREPARATION_LEASE_SECONDS")

        result = runner.run_once(app, now_ms=1_000)

        self.assertEqual(result["claimed"], 1)
        self.assertEqual(repository.last_claim_lease_ms, 360_000)

    def test_run_once_fails_closed_when_runtime_enable_flags_are_not_exact_booleans(self):
        for overrides in (
            {"LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED": "1"},
            {"LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED": 1},
            {"LEARNING_CURRICULUM_PREPARATION_CONTENT_GENERATION_ENABLED": "1"},
            {"LEARNING_CURRICULUM_PREPARATION_CONTENT_GENERATION_ENABLED": 1},
        ):
            with self.subTest(overrides=overrides):
                repository = _FakeRepository()
                runner = self._checkpoint_runner(
                    repository,
                    _FakeCatalog(),
                    clock=_Clock(1_001),
                )

                result = runner.run_once(_app(**overrides), now_ms=1_000)

                self.assertEqual(result, {"claimed": 0, "disabled": True})
                self.assertEqual(repository.claim_calls, 0)

    def test_lost_create_response_reuses_same_shared_request_after_lease_expiry(self):
        repository = _FakeRepository()
        catalog = _FakeCatalog()
        repository.crash_before_apply = True

        runner = self._checkpoint_runner(
            repository,
            catalog,
            clock=_Clock(1_001, 92_002),
        )
        with self.assertRaises(SimulatedProcessCrash):
            runner.run_once(_app(), now_ms=1_000)
        first_request = catalog.create_calls[0]["requestId"]
        self.assertEqual(repository.plan["status"], "running")
        self.assertEqual(repository.plan["stage"], "planning")
        self.assertEqual(repository.plan["next_run_at"], 1_000)
        self.assertEqual(repository.plan["hard_deadline_at"], 121_000)

        repository.expire_lease(now_ms=92_000)
        second = runner.run_once(_app(), now_ms=92_001)

        self.assertEqual(second["sharedBuildRequestId"], first_request)
        self.assertEqual(catalog.create_calls[-1]["requestId"], first_request)
        self.assertEqual(repository.plan["stage"], "generating_content")
        self.assertIsNone(repository.plan["hard_deadline_at"])

    def test_checkpoint_deadline_stops_before_second_adapter_call(self):
        repository = _FakeRepository()
        catalog = _FakeCatalog([ApiError("unavailable", "secret", 503)])
        runner = self._checkpoint_runner(repository, catalog, clock=_Clock(1_001))
        runner.run_once(_app(), now_ms=1_000)

        result = runner.run_once(_app(), now_ms=121_000)

        self.assertEqual(result["errorCode"], "preparation_stage_deadline_exceeded")
        self.assertEqual(repository.plan["status"], "failed")
        self.assertEqual(len(catalog.create_calls), 1)

    def test_post_adapter_clock_deadline_fails_closed_before_result_transaction(self):
        repository = _FakeRepository()
        catalog = _FakeCatalog()
        runner = self._checkpoint_runner(
            repository, catalog, clock=_Clock(1_001, 121_001)
        )

        result = runner.run_once(_app(), now_ms=1_000)

        self.assertEqual(result["errorCode"], "preparation_stage_deadline_exceeded")
        self.assertIsNone(repository.plan["catalog_build_id"])
        self.assertEqual(len(catalog.create_calls), 1)

    def test_transient_unavailable_defers_and_reuses_request_and_deadline(self):
        repository = _FakeRepository()
        catalog = _FakeCatalog([ApiError("unavailable", "secret", 503)])
        runner = self._checkpoint_runner(
            repository, catalog, clock=_Clock(1_001, 1_001, 31_002)
        )
        first = runner.run_once(_app(), now_ms=1_000)
        request_id = catalog.create_calls[0]["requestId"]
        deadline = repository.plan["hard_deadline_at"]

        self.assertEqual(first["status"], "retry_wait")
        self.assertEqual(repository.plan["resume_stage"], "planning")
        self.assertEqual(repository.plan["next_run_at"], 31_001)
        second = runner.run_once(_app(), now_ms=31_001)
        self.assertEqual(second["sharedBuildRequestId"], request_id)
        self.assertEqual(catalog.create_calls[-1]["requestId"], request_id)
        self.assertEqual(deadline, 121_000)
        self.assertIsNone(repository.plan["hard_deadline_at"])

    def test_explicit_transient_error_is_deferred(self):
        repository = _FakeRepository()

        class Adapter:
            supported_stages = frozenset({"queued", "planning"})

            def advance(self, plan, *, now_ms, heartbeat):
                raise PreparationTransientError("temporary")

        runner = LearningCurriculumPreparationRunner(
            repository=repository, adapter=Adapter(), clock=_Clock(1_001)
        )
        result = runner.run_once(_app(), now_ms=1_000)
        self.assertEqual(result["status"], "retry_wait")

    def test_v2_content_connection_reset_recovers_catalog_first_without_plan_defer(self):
        repository = _FakeRepository()
        repository.plan.update(
            status="running",
            stage="generating_content",
            catalog_build_id="catalog_build_shared",
            catalog_release_id="catalog_release_shared",
            next_run_at=1_000,
            work_unit_kind=None,
        )

        class Adapter:
            supported_stages = frozenset({"generating_content"})

            def advance(self, plan, *, now_ms, heartbeat):
                del plan, now_ms, heartbeat
                raise ConnectionResetError("lost response after catalog CAS")

        runner = LearningCurriculumPreparationRunner(
            repository=repository,
            adapter=Adapter(),
            clock=_Clock(1_001),
        )
        with patch.object(
            repository,
            "defer_claim",
            wraps=repository.defer_claim,
        ) as defer, patch.object(
            repository,
            "reconcile_shared_build",
            wraps=repository.reconcile_shared_build,
        ) as reconcile, patch.object(
            repository,
            "release_content_continuation",
            wraps=repository.release_content_continuation,
        ) as release:
            result = runner.run_once(_app(), now_ms=1_000)

        self.assertEqual(result["resultCode"], "progressed", result)
        self.assertEqual(result["status"], "running", result)
        self.assertEqual(repository.plan["stage"], "generating_content")
        self.assertIsNone(repository.plan["lease_token"])
        self.assertIsNone(repository.plan["hard_deadline_at"])
        self.assertEqual(defer.call_count, 0)
        self.assertEqual(reconcile.call_count, 1)
        self.assertEqual(release.call_count, 1)

    def test_deterministic_catalog_conflict_is_terminal(self):
        repository = _FakeRepository()
        catalog = _FakeCatalog([ApiError("catalog_build_request_conflict", "x", 409)])
        runner = self._checkpoint_runner(repository, catalog, clock=_Clock(1_001))

        result = runner.run_once(_app(), now_ms=1_000)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errorCode"], "preparation_catalog_conflict")

    def test_invalid_adapter_result_is_terminal_not_left_running(self):
        repository = _FakeRepository()

        class InvalidAdapter:
            supported_stages = frozenset({"queued", "planning"})

            def advance(self, plan, *, now_ms, heartbeat):
                return PreparationStageResult(
                    next_status="queued",
                    next_stage="unknown_stage",
                    ready_course_count=0,
                    failed_course_count=0,
                    subject_progress=_subject_progress(),
                    next_run_at=now_ms,
                )

        runner = LearningCurriculumPreparationRunner(
            repository=repository,
            adapter=InvalidAdapter(),
            clock=_Clock(1_001),
        )
        result = runner.run_once(_app(), now_ms=1_000)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errorCode"], "preparation_validation_failed")

    def test_late_token_cannot_persist_adapter_result(self):
        repository = _FakeRepository()
        catalog = _FakeCatalog()
        repository.replace_token_before_apply = True

        runner = self._checkpoint_runner(
            repository,
            catalog,
            clock=_Clock(1_001),
        )
        result = runner.run_once(_app(), now_ms=1_000)
        self.assertEqual(result["status"], "stale")
        self.assertIsNone(repository.plan["catalog_build_id"])
        self.assertEqual(repository.events, [])

    def test_fake_adapter_advances_all_stages_to_ready_without_provider_calls(self):
        repository = _FakeRepository()
        adapter = _FakeProgressAdapter(repository)
        runner = LearningCurriculumPreparationRunner(
            repository=repository,
            adapter=adapter,
            clock=_Clock(*range(1_001, 1_020)),
        )

        for offset in range(7):
            runner.run_once(_app(), now_ms=1_000 + offset)

        self.assertEqual(repository.plan["status"], "ready")
        self.assertEqual(repository.plan["stage"], "completed")
        self.assertEqual(
            adapter.calls,
            [
                "planning",
                "generating_content",
                "building_classrooms",
                "generating_speech",
                "validating",
                "publishing",
            ],
        )
        self.assertEqual(adapter.provider.call_count, 0)
        for field in (
            "lease_token",
            "lease_expires_at",
            "heartbeat_at",
            "next_run_at",
            "hard_deadline_at",
            "resume_stage",
        ):
            self.assertIsNone(repository.plan[field], field)

    def test_disabled_and_testing_gate_precedes_adapter_construction_and_claim(self):
        for app in (
            _app(LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED=False),
            _app(TESTING=True),
        ):
            repository = _FakeRepository()
            constructions = []
            runner = LearningCurriculumPreparationRunner(
                repository=repository,
                adapter_factory=lambda _app: constructions.append(True),
            )
            result = runner.run_once(app, now_ms=1_000)
            runner.start(app)
            self.assertEqual(result["claimed"], 0)
            self.assertEqual(repository.claim_calls, 0)
            self.assertEqual(constructions, [])

    def test_checkpoint_factory_constructs_no_generation_or_provider_dependency(self):
        from services import service_factory

        app = _app(DATABASE_URL="mysql+pymysql://unused:unused@127.0.0.1/unused")
        with app.app_context(), patch.object(
            service_factory,
            "dynamic_learning_course_generation_service",
            side_effect=AssertionError("generation factory must not be called"),
        ), patch.object(
            service_factory,
            "lesson_package_service",
            side_effect=AssertionError("package/provider factory must not be called"),
        ):
            adapter = service_factory.learning_curriculum_preparation_checkpoint_adapter()

        self.assertIsNone(adapter.catalog_service.dynamic_generation_service)
        self.assertIsNone(adapter.catalog_service.lesson_package_service)
        self.assertIs(
            adapter.repository.content_proof_auditor.__self__,
            adapter.catalog_service,
        )
        self.assertEqual(
            adapter.repository.content_proof_auditor.__name__,
            "audit_locked_content_proofs",
        )
        self.assertIs(
            adapter.repository.content_dispatch_graph_auditor.__self__,
            adapter.catalog_service,
        )
        self.assertEqual(
            adapter.repository.content_dispatch_graph_auditor.__name__,
            "audit_content_host_retry_graph",
        )

    def test_checkpoint_factory_freezes_exact_secret_free_seven_key_profile(self):
        from services import service_factory

        app = _app(
            DATABASE_URL="mysql+pymysql://unused:unused@127.0.0.1/unused",
            AI_PROVIDER="kimi",
            AI_MODEL="moonshot-v1-8k",
            AI_BASE_URL="https://api.moonshot.cn/v1",
            AI_API_KEY="CONFIG_SECRET_SENTINEL",
            OPENMAIC_FULL_RUNTIME_INTERNAL_URL="http://127.0.0.1:3100",
            INTERNAL_API_TOKEN="OPENMAIC_CONFIG_TOKEN_SENTINEL",
        )
        app.config.pop("LEARNING_CURRICULUM_PREPARATION_LEASE_SECONDS")
        expected = {
            "name": "openmaic_runtime",
            "model": "courseware-v2",
            "baseUrl": "http://127.0.0.1:3100",
            "apiKeyEnv": "INTERNAL_API_TOKEN",
            "timeoutMs": 300_000,
            "maxTokens": 8_000,
            "temperature": 0.6,
        }
        with app.app_context(), patch.dict(
            os.environ,
            {
                "APP_AI_API_KEY": "ENV_SECRET_SENTINEL",
                "DEEPSEEK_API_KEY": "OPENMAIC_PROVIDER_SECRET_SENTINEL",
                "INTERNAL_API_TOKEN": "OPENMAIC_ENV_TOKEN_SENTINEL",
            },
            clear=False,
        ):
            adapter = (
                service_factory.learning_curriculum_preparation_checkpoint_adapter()
            )
            public_repository = (
                service_factory.learning_curriculum_preparation_repository()
            )

        profiles = adapter.catalog_service.question_phase_provider_profiles
        self.assertEqual(set(profiles), {"generator", "verifier"})
        self.assertEqual(profiles["generator"], expected)
        self.assertEqual(profiles["verifier"], expected)
        self.assertEqual(set(profiles["generator"]), set(expected))
        phase_adapter = (
            adapter.catalog_service.staged_content_candidate_generator._adapter
        )
        self.assertEqual(phase_adapter.provider_name, expected["name"])
        self.assertEqual(phase_adapter.model_name, expected["model"])
        self.assertEqual(phase_adapter.base_url, expected["baseUrl"])
        self.assertEqual(phase_adapter.api_key_env, "INTERNAL_API_TOKEN")
        self.assertEqual(phase_adapter.provider_timeout_ms, 300_000)
        self.assertEqual(phase_adapter.max_tokens, 8_000)
        self.assertEqual(phase_adapter.temperature, 0.6)
        self.assertEqual(phase_adapter.process_timeout_seconds, 305.0)
        self.assertEqual(phase_adapter.required_phase_budget_ms, 315_000)
        self.assertEqual(adapter.plan_lease_ms, 360_000)
        self.assertIsNot(public_repository, adapter.repository)
        self.assertIsNone(public_repository.content_proof_auditor)
        self.assertIsNone(public_repository.content_parent_retry_auditor)
        runner = LearningCurriculumPreparationRunner()
        with app.app_context():
            execution_repository, resolved_adapter = runner._resolve_dependencies(app)
        self.assertIs(resolved_adapter, adapter)
        self.assertIs(execution_repository, adapter.repository)
        secret_free = json.dumps(
            profiles,
            ensure_ascii=False,
            sort_keys=True,
        ) + repr(vars(phase_adapter))
        self.assertNotIn("CONFIG_SECRET_SENTINEL", secret_free)
        self.assertNotIn("ENV_SECRET_SENTINEL", secret_free)
        self.assertNotIn("OPENMAIC_PROVIDER_SECRET_SENTINEL", secret_free)
        self.assertNotIn("api.moonshot.cn", secret_free)

    def test_checkpoint_factory_keeps_camera_kimi_out_of_learning_profile(self):
        from services import service_factory

        app = _app(
            DATABASE_URL="mysql+pymysql://unused:unused@127.0.0.1/unused",
            AI_PROVIDER="kimi",
            AI_MODEL="kimi-k2.6",
            AI_BASE_URL="https://api.moonshot.cn/v1",
            AI_API_KEY="CONFIG_SECRET_SENTINEL",
            OPENMAIC_FULL_RUNTIME_INTERNAL_URL="http://127.0.0.1:3100/",
            INTERNAL_API_TOKEN="OPENMAIC_CONFIG_TOKEN_SENTINEL",
        )
        with app.app_context():
            profile = service_factory._checkpoint_question_phase_profile()
            checkpoint = (
                service_factory.learning_curriculum_preparation_checkpoint_adapter()
            )

        self.assertIsNotNone(profile)
        self.assertEqual(profile["name"], "openmaic_runtime")
        self.assertEqual(profile["model"], "courseware-v2")
        self.assertEqual(profile["baseUrl"], "http://127.0.0.1:3100")
        self.assertEqual(profile["apiKeyEnv"], "INTERNAL_API_TOKEN")
        self.assertEqual(profile["temperature"], 0.6)
        phase_adapter = (
            checkpoint.catalog_service.staged_content_candidate_generator._adapter
        )
        self.assertEqual(phase_adapter.provider_name, "openmaic_runtime")
        self.assertEqual(phase_adapter.model_name, "courseware-v2")
        self.assertEqual(phase_adapter.api_key_env, "INTERNAL_API_TOKEN")
        self.assertEqual(phase_adapter.temperature, 0.6)

    def test_default_runner_dependency_resolution_is_provider_free(self):
        from services import service_factory

        app = _app(DATABASE_URL="mysql+pymysql://unused:unused@127.0.0.1/unused")
        forbidden = (
            "sms_provider",
            "auth_service",
            "dynamic_learning_course_generation_service",
            "learning_content_generation_service",
            "lesson_package_service",
            "ai_text_provider",
        )
        patches = [
            patch.object(
                service_factory,
                name,
                side_effect=AssertionError(f"{name} must not be called"),
            )
            for name in forbidden
        ]
        for active_patch in patches:
            active_patch.start()
        try:
            repository, adapter = LearningCurriculumPreparationRunner()._resolve_dependencies(
                app
            )
        finally:
            for active_patch in reversed(patches):
                active_patch.stop()

        self.assertEqual(
            repository.database.database_url, app.config["DATABASE_URL"]
        )
        self.assertIsInstance(adapter, CheckpointSharedBuildAdapter)

    def test_malformed_subject_progress_fails_terminal_with_fixed_safe_error(self):
        for malformed in ([], "not-json"):
            with self.subTest(malformed=malformed):
                repository = _FakeRepository()
                repository.plan["subject_progress_json"] = malformed
                catalog = _FakeCatalog()
                runner = self._checkpoint_runner(
                    repository, catalog, clock=_Clock(1_001)
                )

                result = runner.run_once(_app(), now_ms=1_000)

                self.assertEqual(result["status"], "failed")
                self.assertEqual(
                    result["errorCode"], "preparation_validation_failed"
                )
                self.assertEqual(repository.plan["status"], "failed")
                self.assertEqual(
                    repository.plan["error_message_safe"],
                    "部分课程未通过系统校验，请重新准备",
                )

    def test_start_stop_restart_is_synchronized_and_reloader_guarded(self):
        repository = _FakeRepository()
        repository.plan["next_run_at"] = 10**15
        adapter = _FakeProgressAdapter(repository)
        runner = LearningCurriculumPreparationRunner(
            repository=repository, adapter=adapter, clock=_Clock(1_000)
        )
        app = _app()

        runner.start(app)
        first_thread = runner.thread
        runner.start(app)
        self.assertIs(runner.thread, first_thread)
        self.assertTrue(first_thread.is_alive())
        self.assertTrue(runner.stop(timeout=1))
        self.assertFalse(first_thread.is_alive())
        runner.start(app)
        second_thread = runner.thread
        self.assertIsNot(second_thread, first_thread)
        self.assertTrue(runner.stop(timeout=1))

        debug_app = _app(DEBUG=True)
        with patch.dict("os.environ", {}, clear=True):
            runner.start(debug_app)
        self.assertIsNone(runner.thread)

    def test_background_exception_is_safe_observed_and_loop_continues(self):
        repository = _FakeRepository()
        adapter = _FakeProgressAdapter(repository)
        runner = LearningCurriculumPreparationRunner(
            repository=repository,
            adapter=adapter,
            clock=_Clock(1_000, 1_001, 1_002, 1_003),
        )
        secret = "SENTINEL_PROVIDER_BODY_DO_NOT_LOG"
        calls = []
        first_observation = []

        def run_once(_app, *, now_ms):
            calls.append(now_ms)
            if len(calls) == 1:
                raise RuntimeError(secret)
            first_observation.append(dict(runner._observation))
            runner._stop.set()
            return {"claimed": 0}

        runner.run_once = run_once
        with self.assertLogs(
            "services.learning_curriculum_preparation_runner",
            level="WARNING",
        ) as captured:
            runner._run(_app(), interval=0)

        self.assertEqual(len(calls), 2)
        self.assertEqual(
            first_observation,
            [
                {
                    "lastRunAt": 1_001,
                    "lastResultCode": "unexpected_exception",
                    "lastStage": None,
                    "lastErrorCode": "preparation_generation_failed",
                }
            ],
        )
        log_text = "\n".join(captured.output)
        self.assertIn("RuntimeError", log_text)
        self.assertIn("preparation_generation_failed", log_text)
        self.assertNotIn(secret, log_text)

    def test_background_tick_scopes_and_releases_application_context(self):
        repository = _FakeRepository()
        adapter = _FakeProgressAdapter(repository)
        runner = LearningCurriculumPreparationRunner(
            repository=repository,
            adapter=adapter,
            clock=_Clock(1_000, 1_001, 1_002),
        )
        app = _app()
        observed = []
        original_advance = adapter.advance

        def advance(plan, *, now_ms, heartbeat):
            observed.append(
                (
                    current_app._get_current_object() is app,
                    now_ms,
                )
            )
            runner._stop.set()
            return original_advance(plan, now_ms=now_ms, heartbeat=heartbeat)

        adapter.advance = advance
        self.assertFalse(has_app_context())

        runner._run(app, interval=0)

        self.assertEqual(observed, [(True, 1_000)])
        self.assertEqual(adapter.calls, ["planning"])
        self.assertFalse(has_app_context())

    def test_default_read_only_status_resolves_repository_without_execution_pipeline(self):
        from services import service_factory

        repository = _FakeRepository()
        repository.count_runner_scope = lambda _conn, **_kwargs: {
            "claimablePlanCount": 1,
            "runningPlanCount": 2,
            "expiredLeaseCount": 3,
        }
        runner = LearningCurriculumPreparationRunner()
        app = _app(
            DATABASE_URL="mysql+pymysql://unused:unused@127.0.0.1/unused"
        )
        with patch.object(
            service_factory,
            "learning_curriculum_preparation_status_repository",
            return_value=repository,
        ) as status_repository, patch.object(
            service_factory,
            "learning_curriculum_preparation_checkpoint_adapter",
            side_effect=AssertionError("status must not resolve the adapter"),
        ), patch.object(
            service_factory,
            "_checkpoint_question_phase_profile",
            side_effect=AssertionError("status must not resolve provider profiles"),
        ):
            status = runner.read_only_status(app, now_ms=5_000)

        self.assertEqual(status_repository.call_count, 1)
        self.assertEqual(
            set(status),
            {
                "lastRunAt",
                "lastResultCode",
                "lastStage",
                "lastErrorCode",
                "claimablePlanCount",
                "runningPlanCount",
                "expiredLeaseCount",
            },
        )


if __name__ == "__main__":
    unittest.main()
