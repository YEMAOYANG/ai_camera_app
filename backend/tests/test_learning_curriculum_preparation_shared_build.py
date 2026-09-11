from __future__ import annotations

from contextlib import contextmanager
from dataclasses import fields
import hashlib
import inspect
import json
import os
import threading
import unittest
from unittest.mock import patch

from flask import Flask

from core.database import Database, DatabaseConnection
from integrations.openmaic_question_adapter import QUESTION_PHASE_IO
from repositories.dynamic_learning_course_repository import (
    DynamicLearningCourseRepository,
)
from repositories.learning_curriculum_preparation_repository import (
    LearningCurriculumPreparationRepository,
    ParentRetryAuthoritySnapshot,
    SharedBuildReconciliationSnapshot,
)
from services.dynamic_learning_course_generation_service import (
    StagedContentCandidateGenerator,
)
from services.learning_catalog_release_service import (
    ContentAdvanceResult,
    ContentDispatchGraphAuditSnapshot,
    ContentProofAuditSnapshot,
    ContentWorkUnitClaim,
    LearningCatalogReleaseService,
)
from services.learning_generated_course_validator import (
    LearningGeneratedCourseValidator,
    PrimaryOneHostGateDependencyError,
)
from services.learning_curriculum_preparation_contract import (
    PREPARATION_SCHEMA_HEADER,
    build_preparation_target,
    preparation_target_fingerprint,
)
from services.learning_curriculum_preparation_runner import (
    CheckpointSharedBuildAdapter,
    LearningCurriculumPreparationRunner,
)
from core.security import now_ms as system_now_ms
from tests.support import fresh_test_config, reset_mysql_test_database
from tests.test_learning_catalog_content_only import (
    _CompletePinyinCanaryAdapter,
    _CountingHostValidator,
    _OutlineOnlyAdapter,
    _RejectingPinyinCanaryAdapter,
)
from tests.test_learning_catalog_content_review_fix2 import (
    _CompletePrimaryOneAdapter,
)
from tests.test_learning_checkpoint_request_path_zero_calls import (
    SIDE_EFFECT_CATEGORIES,
    _RequestPathSideEffectGuard,
)


class _PlanningCatalog:
    def __init__(self):
        self.restricted_calls = 0
        self.public_calls = 0
        self.direct_content_calls = 0

    def create(self, _payload):
        self.public_calls += 1
        raise AssertionError("planning touched the public catalog create path")

    def create_preparation_content_build(self, **kwargs):
        self.direct_content_calls += 1
        raise AssertionError("planning bypassed atomic catalog authority")

    def create_authorized_preparation_content_build(self, **kwargs):
        self.restricted_calls += 1
        return {
            "build": {
                "id": "build-1",
                "requestId": kwargs["request_id"],
                "executionMode": "content_only",
                "stageCeiling": "content_ready",
            },
            "release": {"id": "release-1", "status": "draft"},
        }


class _PlanningRepository:
    def __init__(self, *, authorized=True):
        self.authorized = authorized
        self.authorizations = []
        self.completed = []
        self.reconciled = []

    @contextmanager
    def transaction(self):
        yield object()

    def authorize_shared_build_planning(self, _conn, **kwargs):
        self.authorizations.append(kwargs)
        return self.authorized

    def complete_shared_build_planning(self, _conn, **kwargs):
        self.completed.append(kwargs)
        return True

    def reconcile_shared_build(self, _conn, **kwargs):
        self.reconciled.append(kwargs)
        return 1


class _StatusRepository:
    def __init__(self):
        self.count_calls = 0

    @contextmanager
    def transaction(self):
        yield object()

    def count_runner_scope(
        self,
        _conn,
        *,
        now,
        supported_stages,
        grade_code,
        target_fingerprint,
    ):
        self.count_calls += 1
        self.now = now
        self.supported_stages = supported_stages
        self.grade_code = grade_code
        self.target_fingerprint = target_fingerprint
        return {
            "claimablePlanCount": 4,
            "runningPlanCount": 2,
            "expiredLeaseCount": 1,
        }


class _UpdatedCursor:
    rowcount = 1

    def fetchone(self):
        return {}


class _RecordingConnection:
    def __init__(self):
        self.updates = []

    def execute(self, sql, params=()):
        self.updates.append((sql, tuple(params)))
        return _UpdatedCursor()


class _SqlRecordingProxy:
    def __init__(self, delegate):
        self.delegate = delegate
        self.statements = []

    def execute(self, sql, params=()):
        self.statements.append(sql)
        return self.delegate.execute(sql, params)


class _RowcountCursor:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class _HeartbeatCasConnection:
    def __init__(self, *, item_rowcount, plan_rowcount):
        self.item_rowcount = item_rowcount
        self.plan_rowcount = plan_rowcount
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))
        if "UPDATE learning_catalog_build_items" in sql:
            return _RowcountCursor(self.item_rowcount)
        if "UPDATE learning_curriculum_preparation_plans" in sql:
            return _RowcountCursor(self.plan_rowcount)
        raise AssertionError(sql)


class _HeartbeatAuthorityRepository(LearningCurriculumPreparationRepository):
    def __init__(self, *, item_heartbeat_at, plan_heartbeat_at, plan_lease_at):
        super().__init__(object())
        target = build_preparation_target("primary_1")
        course_target = target["courseTargets"][0]
        digest = hashlib.sha256(
            (
                "build-1:primary_1:"
                f"{course_target['subject']}:{course_target['skillId']}:"
                f"{course_target['variantOrdinal']}"
            ).encode("utf-8")
        ).hexdigest()
        self.target_json = json.dumps(
            target, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        item_id = f"catalog_build_item_{digest[:24]}"
        self.item = {
            "id": item_id,
            "build_job_id": "build-1",
            "release_id": "release-1",
            "grade_code": "primary_1",
            "execution_mode_snapshot": "content_only",
            "content_manifest_version_snapshot": (
                "mira.learning.preparation-target.v2"
            ),
            "status": "processing",
            "attempt_count": 1,
            "content_claim_attempt_ordinal": 1,
            "claim_origin_status": "pending",
            "generation_request_id": f"catalog_gen_{digest[:48]}",
            "active_generation_request_id": f"catalog_gen_{digest[:48]}",
            "curriculum_version": target["curriculumVersion"],
            "subject": course_target["subject"],
            "subject_ordinal": course_target["subjectOrdinal"],
            "skill_id": course_target["skillId"],
            "boundary_ordinal": course_target["boundaryOrdinal"],
            "boundary_version": course_target["boundaryVersion"],
            "variant_ordinal": course_target["variantOrdinal"],
            "package_attempt_count": 0,
            "active_package_request_id": None,
            "package_id": None,
            "package_version": None,
            "content_phase": "outline",
            "content_gate_status": "not_started",
            "content_gate_attempt_count": 0,
            "content_gate_passed_at": None,
            "content_lease_token": "content-lease",
            "content_lease_expires_at": 2_000,
            "content_attempt_started_at": 200,
            "content_provider_attempt_hard_deadline_at": 1_800_200,
            "content_work_unit_deadline_at": 2_000,
            "content_heartbeat_at": item_heartbeat_at,
        }
        self.plan = {
            "id": "plan-1",
            "status": "running",
            "stage": "generating_content",
            "lease_token": "plan-lease",
            "lease_expires_at": plan_lease_at,
            "heartbeat_at": plan_heartbeat_at,
            "hard_deadline_at": 2_000,
            "work_unit_kind": "provider_phase",
            "bound_catalog_item_id": item_id,
            "bound_content_attempt_ordinal": 1,
            "bound_content_phase": "outline",
        }

    def _lock_shared_authority(self, _conn, **_kwargs):
        return (
            {"id": "release-1"},
            {
                "id": "build-1",
                "status": "running",
                "error_code": None,
                "error_message_safe": None,
                "completed_at": None,
                "target_spec_json": self.target_json,
            },
            [dict(self.item)],
            {},
            dict(self.plan),
        )

    @classmethod
    def _shared_authority_matches(cls, **_kwargs):
        return True


class _BoundaryAuthorityRepository(LearningCurriculumPreparationRepository):
    def __init__(self):
        super().__init__(object())
        target = build_preparation_target("primary_1")
        course_target = target["courseTargets"][0]
        digest = hashlib.sha256(
            (
                "build-1:primary_1:"
                f"{course_target['subject']}:{course_target['skillId']}:"
                f"{course_target['variantOrdinal']}"
            ).encode("utf-8")
        ).hexdigest()
        self.target_json = json.dumps(
            target, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        item_id = f"catalog_build_item_{digest[:24]}"
        self.plan = {
            "id": "plan-1",
            "family_id": "family-1",
            "child_id": "child-1",
            "grade_code": "primary_1",
            "grade_selection_revision": 1,
            "target_spec_json": json.dumps(
                build_preparation_target("primary_1"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "target_fingerprint": "f" * 64,
            "catalog_build_id": "build-1",
            "catalog_release_id": "release-1",
            "status": "running",
            "stage": "generating_content",
            "lease_token": "plan-lease",
            "lease_expires_at": 1_000,
            "heartbeat_at": 999,
            "hard_deadline_at": 1_000,
            "work_unit_kind": "provider_phase",
            "bound_catalog_item_id": item_id,
            "bound_content_attempt_ordinal": 1,
            "bound_content_phase": "outline",
        }
        self.item = {
            "id": item_id,
            "build_job_id": "build-1",
            "release_id": "release-1",
            "grade_code": "primary_1",
            "execution_mode_snapshot": "content_only",
            "content_manifest_version_snapshot": (
                "mira.learning.preparation-target.v2"
            ),
            "status": "processing",
            "attempt_count": 1,
            "content_claim_attempt_ordinal": 1,
            "claim_origin_status": "pending",
            "generation_request_id": f"catalog_gen_{digest[:48]}",
            "active_generation_request_id": f"catalog_gen_{digest[:48]}",
            "curriculum_version": target["curriculumVersion"],
            "subject": course_target["subject"],
            "subject_ordinal": course_target["subjectOrdinal"],
            "skill_id": course_target["skillId"],
            "boundary_ordinal": course_target["boundaryOrdinal"],
            "boundary_version": course_target["boundaryVersion"],
            "variant_ordinal": course_target["variantOrdinal"],
            "package_attempt_count": 0,
            "active_package_request_id": None,
            "package_id": None,
            "package_version": None,
            "content_phase": "outline",
            "content_gate_status": "not_started",
            "content_gate_attempt_count": 0,
            "content_gate_passed_at": None,
            "content_lease_token": "content-lease",
            "content_lease_expires_at": 1_000,
            "content_attempt_started_at": 100,
            "content_provider_attempt_hard_deadline_at": 1_800_100,
            "content_work_unit_deadline_at": 1_000,
            "content_heartbeat_at": 999,
        }

    def get_plan(self, _conn, _plan_id, *, for_update=False):
        del for_update
        return dict(self.plan)

    def _lock_shared_authority(self, _conn, **kwargs):
        items = [dict(self.item)] if kwargs.get("catalog_item_id") else []
        return (
            {"id": "release-1"},
            {
                "id": "build-1",
                "status": "running",
                "error_code": None,
                "error_message_safe": None,
                "completed_at": None,
                "target_spec_json": self.target_json,
            },
            items,
            {},
            dict(self.plan),
        )

    @classmethod
    def _shared_authority_matches(cls, **_kwargs):
        return True


class _StrictHeartbeatPredicateConnection:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))
        strict = (
            "lease_expires_at > ?" in sql
            and "hard_deadline_at > ?" in sql
        )
        return _RowcountCursor(1 if strict else 0)


class _CatalogFirstDependencyRepository(
    LearningCurriculumPreparationRepository
):
    def __init__(self):
        super().__init__(object())
        self.catalog_lock_calls = []
        self.plan = {
            **_planning_plan(),
            "stage": "generating_content",
            "catalog_build_id": "build-1",
            "catalog_release_id": "release-1",
            "lease_expires_at": 2_000,
            "work_unit_kind": "provider_phase",
            "bound_catalog_item_id": "item-1",
            "bound_content_attempt_ordinal": 1,
            "bound_content_phase": "outline",
        }
        self.plan["target_spec_json"] = (
            '{"schemaVersion":"mira.learning.preparation-target.v2"}'
        )

    def get_plan(self, _conn, plan_id, *, for_update=False):
        if for_update and not self.catalog_lock_calls:
            raise AssertionError("dependency defer locked plan before catalog")
        self.assert_plan_id = plan_id
        return dict(self.plan)

    def _lock_shared_authority(self, _conn, **kwargs):
        self.catalog_lock_calls.append(kwargs)
        return (
            {},
            {
                "status": "running",
                "error_code": None,
                "error_message_safe": None,
                "completed_at": None,
            },
            [
                {
                    "id": "item-1",
                    "build_job_id": "build-1",
                    "status": "processing",
                    "attempt_count": 1,
                    "content_phase": "outline",
                    "content_work_unit_deadline_at": 121_000,
                }
            ],
            {},
            dict(self.plan),
        )

    @classmethod
    def _shared_authority_matches(cls, **_kwargs):
        return True

    @classmethod
    def _dependency_retry_binding_matches(cls, **_kwargs):
        return True


class _MutableClock:
    def __init__(self, value: int):
        self.value = value

    def __call__(self):
        return self.value


class _BindingObservedPinyinAdapter(_CompletePinyinCanaryAdapter):
    def __init__(self, database: Database):
        super().__init__()
        self.database = database
        self.binding_observations = []

    def execute_phase(self, prepared):
        with self.database.transaction() as conn:
            item = conn.execute(
                """
                SELECT * FROM learning_catalog_build_items
                WHERE id = ? LIMIT 1
                """,
                (prepared.command.build_item_id,),
            ).fetchone()
            plan = conn.execute(
                """
                SELECT * FROM learning_curriculum_preparation_plans
                WHERE bound_catalog_item_id = ? AND lease_token IS NOT NULL
                LIMIT 1
                """,
                (prepared.command.build_item_id,),
            ).fetchone()
        if plan is None or item is None:
            raise AssertionError("Provider began before plan/item binding committed")
        self.binding_observations.append(
            {
                "planId": str(plan["id"]),
                "itemId": str(plan["bound_catalog_item_id"]),
                "attempt": int(plan["bound_content_attempt_ordinal"]),
                "phase": str(plan["bound_content_phase"]),
                "workKind": str(plan["work_unit_kind"]),
                "planDeadline": int(plan["hard_deadline_at"]),
                "itemDeadline": int(item["content_work_unit_deadline_at"]),
            }
        )
        return super().execute_phase(prepared)


class _BindingObservedHostValidator:
    def __init__(self, database: Database):
        self.database = database
        self.delegate = LearningGeneratedCourseValidator()
        self.binding_observations = []

    def validate_primary_one_host_gate(self, *args, **kwargs):
        identity = kwargs["identity"]
        item_id = str(identity.catalog_item_id)
        if not self.binding_observations:
            with self.database.transaction() as conn:
                item = conn.execute(
                    """
                    SELECT * FROM learning_catalog_build_items
                    WHERE id = ? LIMIT 1
                    """,
                    (item_id,),
                ).fetchone()
                plan = conn.execute(
                    """
                    SELECT * FROM learning_curriculum_preparation_plans
                    WHERE bound_catalog_item_id = ? AND lease_token IS NOT NULL
                    LIMIT 1
                    """,
                    (item_id,),
                ).fetchone()
            if plan is None or item is None:
                raise AssertionError("Host began before plan/item binding committed")
            self.binding_observations.append(
                {
                    "planId": str(plan["id"]),
                    "itemId": str(plan["bound_catalog_item_id"]),
                    "workKind": str(plan["work_unit_kind"]),
                    "phase": str(plan["bound_content_phase"]),
                    "planDeadline": int(plan["hard_deadline_at"]),
                    "itemDeadline": int(item["content_work_unit_deadline_at"]),
                }
            )
        return self.delegate.validate_primary_one_host_gate(*args, **kwargs)

    def validate_primary_one_accepted_receipt(self, proof):
        return self.delegate.validate_primary_one_accepted_receipt(proof)


class _HostDependencyValidator:
    def __init__(self):
        self.delegate = LearningGeneratedCourseValidator()
        self.host_calls = 0

    def validate_primary_one_host_gate(self, *args, **kwargs):
        del args, kwargs
        self.host_calls += 1
        raise PrimaryOneHostGateDependencyError("test-only host dependency")

    def validate_primary_one_accepted_receipt(self, proof):
        return self.delegate.validate_primary_one_accepted_receipt(proof)


class _HeartbeatRepository:
    def __init__(self):
        self.heartbeat_calls = 0
        self.bound_claims = []
        self.reconcile_calls = 0
        self.reconcile_arguments = []
        self.release_calls = 0
        self.defer_calls = 0
        self.exact_owner_handoff = True

    @contextmanager
    def transaction(self):
        yield object()

    def bind_content_work_unit(self, _conn, **kwargs):
        self.bound_claims.append(kwargs)
        return {"id": kwargs["plan_id"]}

    def heartbeat_bound_content_work_unit(self, _conn, **_kwargs):
        self.heartbeat_calls += 1
        return True

    def reconcile_shared_build(self, _conn, **kwargs):
        self.reconcile_calls += 1
        self.reconcile_arguments.append(kwargs)
        return 1

    def reconcile_shared_build_with_owner_outcome(self, _conn, **kwargs):
        self.reconcile_calls += 1
        self.reconcile_arguments.append(kwargs)
        return SharedBuildReconciliationSnapshot(
            updated_count=1,
            exact_owner_handoff=self.exact_owner_handoff,
        )

    def release_content_continuation(self, _conn, **_kwargs):
        self.release_calls += 1
        return True

    def defer_bound_dependency(self, _conn, **_kwargs):
        self.defer_calls += 1
        return True


class _BlockedHeartbeatRepository(_HeartbeatRepository):
    def __init__(self):
        super().__init__()
        self.heartbeat_entered = threading.Event()
        self.heartbeat_unblock = threading.Event()

    def heartbeat_bound_content_work_unit(self, _conn, **_kwargs):
        self.heartbeat_calls += 1
        self.heartbeat_entered.set()
        if not self.heartbeat_unblock.wait(5):
            raise AssertionError("test heartbeat did not unblock")
        return True


class _BlockingClaimCatalog:
    def __init__(self, *, phase: str, work_kind: str):
        self.phase = phase
        self.work_kind = work_kind
        self.claim = None

    def advance_content(
        self,
        build_id,
        *,
        heartbeat,
        bind_work_unit,
        authorize_control_work,
    ):
        del heartbeat, authorize_control_work
        self.claim = ContentWorkUnitClaim(
            build_id=build_id,
            item_id="item-1",
            item_lease_token="content-lease",
            logical_attempt=1,
            content_phase=self.phase,
            work_unit_kind=self.work_kind,
            work_unit_deadline_at=121_000,
        )
        if bind_work_unit(self.claim) is not True:
            raise AssertionError("blocking catalog claim was not bound")
        threading.Event().wait(0.055)
        return ContentAdvanceResult(
            kind="progressed",
            build_id=build_id,
            item_id="item-1",
            content_summary={},
        )


class _ReturnAfterHeartbeatStartsCatalog(_BlockingClaimCatalog):
    def __init__(self, repository):
        super().__init__(phase="outline", work_kind="provider_phase")
        self.repository = repository

    def advance_content(
        self,
        build_id,
        *,
        heartbeat,
        bind_work_unit,
        authorize_control_work,
    ):
        del heartbeat, authorize_control_work
        self.claim = ContentWorkUnitClaim(
            build_id=build_id,
            item_id="item-1",
            item_lease_token="content-lease",
            logical_attempt=1,
            content_phase=self.phase,
            work_unit_kind=self.work_kind,
            work_unit_deadline_at=121_000,
        )
        if bind_work_unit(self.claim) is not True:
            raise AssertionError("blocking catalog claim was not bound")
        if not self.repository.heartbeat_entered.wait(1):
            raise AssertionError("heartbeat guard did not enter callback")
        return ContentAdvanceResult(
            kind="progressed",
            build_id=build_id,
            item_id="item-1",
            content_summary={},
        )


class _ImmediateCatalogResult:
    def __init__(self, kind):
        self.kind = kind

    def advance_content(self, build_id, **_kwargs):
        return ContentAdvanceResult(
            kind=self.kind,
            build_id=build_id,
            item_id=None,
            content_summary={},
        )


class _SimulatedProcessCrash(BaseException):
    pass


class _CrashWindowRepository(LearningCurriculumPreparationRepository):
    def __init__(
        self,
        database,
        *,
        content_proof_auditor,
        content_provider_dependency_auditor,
    ):
        super().__init__(
            database,
            content_proof_auditor=content_proof_auditor,
            content_provider_dependency_auditor=(
                content_provider_dependency_auditor
            ),
        )
        self.mode = None
        self.crashed = False

    def arm(self, mode):
        self.mode = mode
        self.crashed = False

    def reconcile_shared_build(self, conn, **kwargs):
        if self.mode in {
            "before_reconcile",
            "connection_reset_after_catalog_cas",
        } and not self.crashed:
            self.crashed = True
            if self.mode == "connection_reset_after_catalog_cas":
                raise ConnectionResetError("lost response after catalog CAS")
            raise _SimulatedProcessCrash()
        return super().reconcile_shared_build(conn, **kwargs)

    def release_content_continuation(self, conn, **kwargs):
        if self.mode == "before_release" and not self.crashed:
            self.crashed = True
            raise _SimulatedProcessCrash()
        return super().release_content_continuation(conn, **kwargs)


def _planning_plan():
    return {
        "id": "plan-1",
        "family_id": "family-1",
        "child_id": "child-1",
        "grade_code": "primary_1",
        "grade_selection_revision": 7,
        "target_spec_json": {
            "schemaVersion": "mira.learning.preparation-target.v2",
        },
        "target_fingerprint": "f" * 64,
        "shared_build_request_id": "grade-build:" + "f" * 64,
        "status": "running",
        "stage": "planning",
        "lease_token": "plan-lease",
        "hard_deadline_at": 121_000,
        "ready_course_count": 0,
        "failed_course_count": 0,
        "subject_progress_json": {},
    }


def _runner_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        TESTING=False,
        DEBUG=False,
        LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED=True,
        LEARNING_CURRICULUM_PREPARATION_CONTENT_GENERATION_ENABLED=True,
        LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST=["primary_1"],
        LEARNING_CURRICULUM_PREPARATION_LEASE_SECONDS=90,
    )
    return app


class LearningCurriculumPreparationSharedBuildTest(unittest.TestCase):
    def test_parent_retry_authority_is_a_frozen_fact_snapshot(self):
        self.assertEqual(
            [field.name for field in fields(ParentRetryAuthoritySnapshot)],
            [
                "authority_class",
                "provider_dispatch_count",
                "open_or_ambiguous_dispatch_count",
                "failed_safe_dispatch_count",
                "provider_graph_complete",
                "next_work_kind",
                "build_error_code",
            ],
        )
        load = inspect.signature(
            LearningCurriculumPreparationRepository.load_parent_retry_authority
        )
        self.assertEqual(set(load.parameters), {"self", "conn", "plan", "lock"})
        locked = inspect.signature(
            LearningCurriculumPreparationRepository.lock_parent_retry_context
        )
        self.assertEqual(
            set(locked.parameters),
            {"self", "conn", "family_id", "plan_id"},
        )

    def test_parent_retry_context_rechecks_all_plan_authority_after_catalog_locks(self):
        target = build_preparation_target("primary_1")
        target_json = json.dumps(
            target,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        hint = {
            "id": "plan-1",
            "family_id": "family-1",
            "child_id": "child-1",
            "grade_code": "primary_1",
            "grade_selection_revision": 3,
            "target_fingerprint": preparation_target_fingerprint(target),
            "shared_build_request_id": (
                f"grade-build:{preparation_target_fingerprint(target)}"
            ),
            "target_spec_json": target_json,
            "curriculum_version": "cn-primary-2022-v1",
            "preparation_contract_version": (
                "mira.learning.grade-preparation-target.v1"
            ),
            "catalog_build_id": "build-1",
            "catalog_release_id": "release-1",
        }
        family = {"id": "family-1"}
        child = {
            "id": "child-1",
            "family_id": "family-1",
            "grade_code": "primary_1",
            "grade_selection_revision": 3,
        }
        snapshot = ParentRetryAuthoritySnapshot(
            authority_class="host_only_dependency",
            provider_dispatch_count=6,
            open_or_ambiguous_dispatch_count=0,
            failed_safe_dispatch_count=0,
            provider_graph_complete=True,
            next_work_kind="host_gate",
            build_error_code=None,
        )

        class _Cursor:
            def __init__(self, row):
                self.row = row

            def fetchone(self):
                return self.row

        class _ContextConnection:
            def __init__(self, locked_plan):
                self.locked_plan = locked_plan

            def execute(self, sql, _params=()):
                normalized = " ".join(sql.split())
                if "FROM families" in normalized:
                    return _Cursor(family)
                if "FROM children" in normalized:
                    return _Cursor(child)
                if "FOR UPDATE" in normalized:
                    return _Cursor(self.locked_plan)
                return _Cursor(hint)

        mutations = {
            "shared_build_request_id": "grade-build:" + "0" * 64,
            "target_spec_json": "{}",
            "curriculum_version": "drifted-curriculum",
            "preparation_contract_version": "drifted-contract",
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                repository = LearningCurriculumPreparationRepository(object())
                with patch.object(
                    repository,
                    "load_parent_retry_authority",
                    return_value=snapshot,
                ):
                    self.assertIsNone(
                        repository.lock_parent_retry_context(
                            _ContextConnection({**hint, field: value}),
                            family_id="family-1",
                            plan_id="plan-1",
                        )
                    )

    def test_shared_catalog_envelope_rejects_every_planning_drift(self):
        target = build_preparation_target("primary_1")
        target_json = json.dumps(
            target,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        fingerprint = preparation_target_fingerprint(target)
        request_id = f"grade-build:{fingerprint}"
        digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:24]
        build = {
            "id": f"catalog_build_{digest}",
            "request_id": request_id,
            "release_id": f"catalog_release_{digest}",
            "curriculum_version": target["curriculumVersion"],
            "status": "queued",
            "target_spec_json": target_json,
            "total_item_count": 30,
            "ready_item_count": 0,
            "failed_item_count": 0,
            "execution_mode": "content_only",
            "stage_ceiling": "content_ready",
            "content_manifest_version": target["schemaVersion"],
            "canary_manifest_json": json.dumps(
                target["canaryManifest"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "error_code": None,
            "error_message_safe": None,
            "completed_at": None,
        }
        release = {
            "id": f"catalog_release_{digest}",
            "curriculum_version": target["curriculumVersion"],
            "status": "draft",
            "quality_status": "building",
            "required_boundary_count": 10,
            "ready_item_count": 0,
            "activated_at": None,
            "retired_at": None,
        }
        plan = {
            "child_id": "child-1",
            "family_id": "family-1",
            "grade_code": "primary_1",
            "grade_selection_revision": 1,
            "curriculum_version": target["curriculumVersion"],
            "preparation_contract_version": target[
                "preparationContractVersion"
            ],
            "target_spec_json": target_json,
            "target_fingerprint": fingerprint,
            "shared_build_request_id": request_id,
            "catalog_build_id": build["id"],
            "catalog_release_id": release["id"],
        }
        child = {
            "id": "child-1",
            "family_id": "family-1",
            "grade_code": "primary_1",
            "grade_selection_revision": 1,
        }
        self.assertTrue(
            LearningCurriculumPreparationRepository._shared_authority_matches(
                release=release,
                build=build,
                items=None,
                child=child,
                plan=plan,
                target_fingerprint=fingerprint,
            )
        )
        unbound_plan = {
            **plan,
            "catalog_build_id": None,
            "catalog_release_id": None,
        }
        self.assertTrue(
            LearningCurriculumPreparationRepository._shared_authority_matches(
                release=release,
                build=build,
                items=None,
                child=child,
                plan=unbound_plan,
                target_fingerprint=fingerprint,
                allow_unbound_plan_catalog_ids=True,
            )
        )
        self.assertFalse(
            LearningCurriculumPreparationRepository._shared_authority_matches(
                release=release,
                build=build,
                items=None,
                child=child,
                plan=unbound_plan,
                target_fingerprint=fingerprint,
            )
        )
        self.assertFalse(
            LearningCurriculumPreparationRepository._shared_authority_matches(
                release=release,
                build=build,
                items=None,
                child={**child, "grade_code": "primary_2"},
                plan={**plan, "grade_code": "primary_2"},
                target_fingerprint=fingerprint,
            )
        )
        for row_name, field, value in (
            ("build", "id", "catalog_build_drifted"),
            ("build", "curriculum_version", "drifted-curriculum"),
            ("build", "ready_item_count", 1),
            ("build", "ready_item_count", False),
            ("build", "failed_item_count", 1),
            ("build", "failed_item_count", False),
            ("release", "id", "catalog_release_drifted"),
            ("release", "quality_status", "ready"),
            ("release", "required_boundary_count", 9),
            ("release", "ready_item_count", 1),
            ("release", "ready_item_count", False),
            ("release", "activated_at", 1),
            ("release", "retired_at", 1),
        ):
            with self.subTest(row=row_name, field=field):
                changed_build = dict(build)
                changed_release = dict(release)
                target_row = (
                    changed_build if row_name == "build" else changed_release
                )
                target_row[field] = value
                self.assertFalse(
                    LearningCurriculumPreparationRepository._shared_authority_matches(
                        release=changed_release,
                        build=changed_build,
                        items=None,
                        child=child,
                        plan=plan,
                        target_fingerprint=fingerprint,
                    )
                )
        for field in ("catalog_build_id", "catalog_release_id"):
            with self.subTest(half_catalog_pair=field):
                half_bound = dict(plan)
                half_bound[field] = None
                self.assertFalse(
                    LearningCurriculumPreparationRepository._shared_authority_matches(
                        release=release,
                        build=build,
                        items=None,
                        child=child,
                        plan=half_bound,
                        target_fingerprint=fingerprint,
                    )
                )

    def test_shared_authority_lock_rejects_publication_residue(self):
        class _Cursor:
            def __init__(self, *, one=None, all_rows=()):
                self.one = one
                self.all_rows = list(all_rows)

            def fetchone(self):
                return self.one

            def fetchall(self):
                return self.all_rows

        plan = {
            "id": "plan-1",
            "family_id": "family-1",
            "child_id": "child-1",
            "catalog_release_id": "release-1",
        }

        class _Connection:
            def execute(self, sql, _params=()):
                normalized = " ".join(sql.split())
                if "learning_catalog_release_items" in normalized:
                    return _Cursor(one={"release_id": "release-1"})
                if "learning_catalog_releases" in normalized:
                    return _Cursor(one={"id": "release-1"})
                if "learning_catalog_build_jobs" in normalized:
                    return _Cursor(
                        one={"id": "build-1", "release_id": "release-1"}
                    )
                if "FROM children" in normalized:
                    return _Cursor(one={"id": "child-1"})
                if "learning_curriculum_preparation_plans" in normalized:
                    return _Cursor(one=plan)
                raise AssertionError(normalized)

        repository = LearningCurriculumPreparationRepository(object())
        self.assertIsNone(
            repository._lock_shared_authority(
                _Connection(),
                plan_id="plan-1",
                catalog_build_id="build-1",
                catalog_release_id="release-1",
            )
        )

    def test_proof_reconciliation_sql_restores_sealed_target_scalars(self):
        target = build_preparation_target("primary_1")
        target_json = json.dumps(
            target,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        fingerprint = preparation_target_fingerprint(target)
        request_id = f"grade-build:{fingerprint}"
        request_digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[
            :24
        ]
        build_id = f"catalog_build_{request_digest}"
        release_id = f"catalog_release_{request_digest}"
        release = {"id": release_id, "status": "draft"}
        build = {
            "id": build_id,
            "release_id": release_id,
            "request_id": request_id,
            "status": "running",
            "target_spec_json": target_json,
            "execution_mode": "content_only",
            "stage_ceiling": "content_ready",
            "content_manifest_version": target["schemaVersion"],
            "canary_manifest_json": json.dumps(
                target["canaryManifest"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "total_item_count": 30,
        }
        items = [
            {
                "id": f"item-{ordinal}",
                "release_id": release_id,
                "build_job_id": build_id,
                "execution_mode_snapshot": "content_only",
                "content_manifest_version_snapshot": target["schemaVersion"],
                "status": "pending",
                "subject": course_target["subject"],
                "skill_id": course_target["skillId"],
                "variant_ordinal": course_target["variantOrdinal"],
            }
            for ordinal, course_target in enumerate(
                target["courseTargets"], start=1
            )
        ]
        child = {
            "id": "child-1",
            "family_id": "family-1",
            "grade_code": "primary_1",
            "grade_selection_revision": 1,
        }
        plan = {
            "id": "plan-1",
            "family_id": "family-1",
            "child_id": "child-1",
            "grade_code": "primary_1",
            "grade_selection_revision": 1,
            "curriculum_version": target["curriculumVersion"],
            "preparation_contract_version": target[
                "preparationContractVersion"
            ],
            "target_spec_json": target_json,
            "target_fingerprint": fingerprint,
            "shared_build_request_id": request_id,
            "catalog_build_id": build_id,
            "catalog_release_id": release_id,
            "status": "running",
            "stage": "generating_content",
            "lease_token": None,
            "lease_expires_at": None,
            "content_target_count": 29,
            "content_canary_target_count": 2,
        }

        class _Cursor:
            def __init__(self, *, one=None, all_rows=(), rowcount=0):
                self.one = one
                self.all_rows = list(all_rows)
                self.rowcount = rowcount

            def fetchone(self):
                return self.one

            def fetchall(self):
                return self.all_rows

        class _Connection:
            def __init__(self):
                self.update_sql = None

            def execute(self, sql, _params=()):
                normalized = " ".join(sql.split())
                if normalized.startswith("UPDATE learning_curriculum"):
                    self.update_sql = normalized
                    return _Cursor(rowcount=1)
                if normalized.startswith("SELECT release_id FROM learning_catalog_build_jobs"):
                    return _Cursor(one={"release_id": release_id})
                if "FROM learning_catalog_releases" in normalized:
                    return _Cursor(one=release)
                if "FROM learning_catalog_build_jobs" in normalized:
                    return _Cursor(one=build)
                if "FROM learning_catalog_build_items" in normalized:
                    return _Cursor(all_rows=items)
                if normalized.startswith("SELECT id, family_id, child_id"):
                    return _Cursor(
                        all_rows=[
                            {
                                field: plan.get(field)
                                for field in (
                                    "id",
                                    "family_id",
                                    "child_id",
                                    "grade_code",
                                    "grade_selection_revision",
                                    "curriculum_version",
                                    "preparation_contract_version",
                                    "target_spec_json",
                                    "target_fingerprint",
                                    "shared_build_request_id",
                                    "catalog_build_id",
                                    "catalog_release_id",
                                )
                            }
                        ]
                    )
                if "SELECT * FROM children WHERE id IN" in normalized:
                    return _Cursor(all_rows=[child])
                if "SELECT * FROM learning_curriculum_preparation_plans" in normalized:
                    return _Cursor(all_rows=[plan])
                raise AssertionError(normalized)

        snapshot = ContentProofAuditSnapshot(
            build_id=build_id,
            release_id=release_id,
            passed_item_ids=(),
            repairable_item_ids=(),
            terminal_failed_item_ids=(),
        )
        repository = LearningCurriculumPreparationRepository(
            object(),
            content_proof_auditor=lambda _conn, *, build_id: snapshot,
        )
        connection = _Connection()
        self.assertEqual(
            repository.reconcile_shared_build(
                connection,
                build_id=build_id,
                target_fingerprint=fingerprint,
                now=100_000,
            ),
            1,
        )
        self.assertIn("content_target_count = 30", connection.update_sql)
        self.assertIn("content_canary_target_count = 3", connection.update_sql)

    def test_read_only_runner_status_has_exact_safe_select_only_shape(self):
        repository = _StatusRepository()
        runner = LearningCurriculumPreparationRunner(
            repository=repository,
            adapter_factory=lambda _app: (_ for _ in ()).throw(
                AssertionError("read-only status resolved the adapter")
            ),
        )
        app = Flask(__name__)

        status = runner.read_only_status(app, now_ms=5_000)

        self.assertEqual(
            list(status),
            [
                "lastRunAt",
                "lastResultCode",
                "lastStage",
                "lastErrorCode",
                "claimablePlanCount",
                "runningPlanCount",
                "expiredLeaseCount",
            ],
        )
        self.assertEqual(status["claimablePlanCount"], 4)
        self.assertEqual(status["runningPlanCount"], 2)
        self.assertEqual(status["expiredLeaseCount"], 1)
        self.assertEqual(repository.count_calls, 1)

    def test_dependency_defer_locks_catalog_item_before_child_and_plan(self):
        repository = _CatalogFirstDependencyRepository()
        conn = _RecordingConnection()

        deferred = repository.defer_bound_dependency(
            conn,
            plan_id="plan-1",
            plan_lease_token="plan-lease",
            target_fingerprint="f" * 64,
            expected_stage="generating_content",
            next_run_at=1_500,
            now=1_100,
            catalog_build_id="build-1",
            catalog_release_id="release-1",
            work_unit_kind="provider_phase",
            bound_catalog_item_id="item-1",
            bound_content_lease_token="item-lease",
            bound_item_work_unit_deadline_at=121_000,
            bound_logical_attempt=1,
            bound_content_phase="outline",
        )

        self.assertTrue(deferred)
        self.assertEqual(
            repository.catalog_lock_calls,
            [
                {
                    "plan_id": "plan-1",
                    "catalog_build_id": "build-1",
                    "catalog_release_id": "release-1",
                    "catalog_item_id": "item-1",
                    "reject_dispatch_identity": (1, "outline"),
                    "provider_dependency_identity": (1, "outline"),
                    "host_dependency_identity": None,
                    "dependency_authority_out": [],
                }
            ],
        )

    def test_joint_heartbeat_rejects_either_cas_loss_and_accepts_exact_noop(self):
        cases = (
            ("item_cas_loss", 0, 1, 999, 999, 1_500, False),
            ("plan_cas_loss", 1, 0, 999, 999, 1_500, False),
            ("exact_same_ms_noop", 0, 0, 1_000, 1_000, 2_000, True),
        )
        for (
            name,
            item_rowcount,
            plan_rowcount,
            item_heartbeat,
            plan_heartbeat,
            plan_lease,
            expected,
        ) in cases:
            with self.subTest(name=name):
                repository = _HeartbeatAuthorityRepository(
                    item_heartbeat_at=item_heartbeat,
                    plan_heartbeat_at=plan_heartbeat,
                    plan_lease_at=plan_lease,
                )
                conn = _HeartbeatCasConnection(
                    item_rowcount=item_rowcount,
                    plan_rowcount=plan_rowcount,
                )

                actual = repository.heartbeat_bound_content_work_unit(
                    conn,
                    plan_id="plan-1",
                    plan_lease_token="plan-lease",
                    target_fingerprint="f" * 64,
                    catalog_build_id="build-1",
                    catalog_item_id=str(repository.item["id"]),
                    content_lease_token="content-lease",
                    logical_attempt=1,
                    content_phase="outline",
                    item_work_unit_deadline_at=2_000,
                    now=1_000,
                    plan_lease_ms=5_000,
                )

                self.assertEqual(actual, expected)
                self.assertEqual(conn.calls[0][1][0], 2_000)
                if len(conn.calls) == 2:
                    self.assertEqual(conn.calls[1][1][0], 6_000)

    def test_v2_authority_expires_at_exact_lease_or_deadline_boundary(self):
        repository = _BoundaryAuthorityRepository()
        item_id = str(repository.item["id"])
        conn = _RecordingConnection()
        common = {
            "plan_id": "plan-1",
            "plan_lease_token": "plan-lease",
            "target_fingerprint": "f" * 64,
            "catalog_build_id": "build-1",
        }

        planning = dict(repository.plan)
        planning.update(
            {
                "stage": "planning",
                "work_unit_kind": "coordinator",
                "bound_catalog_item_id": None,
                "bound_content_attempt_ordinal": None,
                "bound_content_phase": None,
            }
        )
        repository.plan = planning
        self.assertFalse(
            repository.complete_shared_build_planning(
                conn,
                **common,
                catalog_release_id="release-1",
                now=1_000,
                next_run_at=1_001,
            )
        )

        repository.plan.update(
            {
                "stage": "generating_content",
                "work_unit_kind": "coordinator",
            }
        )
        self.assertIsNone(
            repository.bind_content_work_unit(
                conn,
                **common,
                catalog_item_id=item_id,
                content_lease_token="content-lease",
                logical_attempt=1,
                content_phase="outline",
                item_work_unit_deadline_at=1_000,
                now=1_000,
            )
        )
        self.assertFalse(
            repository.authorize_content_control_work(
                conn,
                **common,
                now=1_000,
            )
        )

        repository.plan.update(
            {
                "work_unit_kind": "provider_phase",
                "bound_catalog_item_id": item_id,
                "bound_content_attempt_ordinal": 1,
                "bound_content_phase": "outline",
            }
        )
        self.assertFalse(
            repository.heartbeat_bound_content_work_unit(
                conn,
                **common,
                catalog_item_id=item_id,
                content_lease_token="content-lease",
                logical_attempt=1,
                content_phase="outline",
                item_work_unit_deadline_at=1_000,
                now=1_000,
                plan_lease_ms=90_000,
            )
        )
        self.assertFalse(
            repository.release_content_continuation(
                conn,
                **common,
                next_run_at=1_001,
                now=1_000,
            )
        )
        self.assertFalse(
            repository.defer_bound_dependency(
                conn,
                plan_id="plan-1",
                plan_lease_token="plan-lease",
                target_fingerprint="f" * 64,
                expected_stage="generating_content",
                next_run_at=1_000,
                now=1_000,
                catalog_build_id="build-1",
                catalog_release_id="release-1",
                work_unit_kind="coordinator",
                bound_catalog_item_id=None,
            )
        )
        self.assertFalse(
            repository._claim_matches(
                repository.plan,
                lease_token="plan-lease",
                target_fingerprint="f" * 64,
                expected_stage="generating_content",
                now=1_000,
            )
        )

        heartbeat_conn = _StrictHeartbeatPredicateConnection()
        self.assertTrue(
            repository.heartbeat(
                heartbeat_conn,
                plan_id="plan-1",
                lease_token="plan-lease",
                target_fingerprint="f" * 64,
                now=999,
                lease_ms=90_000,
            )
        )

    def test_bind_and_heartbeat_reject_locked_item_or_build_authority_drift(self):
        valid = _BoundaryAuthorityRepository()
        valid_item_id = str(valid.item["id"])
        valid.plan.update(
            {
                "lease_expires_at": 2_000,
                "hard_deadline_at": 2_000,
                "work_unit_kind": "coordinator",
            }
        )
        self.assertIsNotNone(
            valid.bind_content_work_unit(
                _RecordingConnection(),
                plan_id="plan-1",
                plan_lease_token="plan-lease",
                target_fingerprint="f" * 64,
                catalog_build_id="build-1",
                catalog_item_id=valid_item_id,
                content_lease_token="content-lease",
                logical_attempt=1,
                content_phase="outline",
                item_work_unit_deadline_at=1_000,
                now=999,
            )
        )
        common_mutations = {
            "release": {"release_id": "wrong-release"},
            "grade": {"grade_code": "primary_2"},
            "mode": {"execution_mode_snapshot": "full"},
            "manifest": {"content_manifest_version_snapshot": "wrong"},
            "curriculum": {"curriculum_version": "wrong"},
            "subject": {"subject": "math"},
            "subject_ordinal": {"subject_ordinal": 2},
            "skill": {"skill_id": "wrong-skill"},
            "boundary_ordinal": {"boundary_ordinal": 2},
            "boundary_version": {"boundary_version": "wrong-boundary"},
            "variant": {"variant_ordinal": 2},
            "generation_request": {"generation_request_id": "wrong-request"},
            "item_id": {"id": "catalog_build_item_wrong"},
            "claim_ordinal": {"content_claim_attempt_ordinal": 2},
            "active_request": {
                "active_generation_request_id": "wrong-request"
            },
            "attempt_bool": {"attempt_count": True},
            "attempt_start": {"content_attempt_started_at": 0},
        }
        other_target = build_preparation_target("primary_1")[
            "courseTargets"
        ][1]
        other_digest = hashlib.sha256(
            (
                "build-1:primary_1:"
                f"{other_target['subject']}:{other_target['skillId']}:"
                f"{other_target['variantOrdinal']}"
            ).encode("utf-8")
        ).hexdigest()
        common_mutations["canonical_duplicate_identity"] = {
            "id": valid_item_id,
            "generation_request_id": f"catalog_gen_{other_digest[:48]}",
            "active_generation_request_id": f"catalog_gen_{other_digest[:48]}",
            "curriculum_version": build_preparation_target("primary_1")[
                "curriculumVersion"
            ],
            "subject": other_target["subject"],
            "subject_ordinal": other_target["subjectOrdinal"],
            "skill_id": other_target["skillId"],
            "boundary_ordinal": other_target["boundaryOrdinal"],
            "boundary_version": other_target["boundaryVersion"],
            "variant_ordinal": other_target["variantOrdinal"],
        }
        provider_mutations = {
            **common_mutations,
            "outer_missing": {
                "content_provider_attempt_hard_deadline_at": None
            },
            "outer_beyond_bounded_continuation": {
                "content_provider_attempt_hard_deadline_at": 5_400_101
            },
            "gate_status": {"content_gate_status": "pending"},
            "gate_ordinal": {"content_gate_attempt_count": 1},
        }
        for name, mutation in provider_mutations.items():
            with self.subTest(kind="provider", drift=name):
                repository = _BoundaryAuthorityRepository()
                repository.plan["lease_expires_at"] = 2_000
                repository.plan["hard_deadline_at"] = 2_000
                repository.plan["work_unit_kind"] = "coordinator"
                repository.item.update(mutation)
                item_id = str(repository.item["id"])
                conn = _RecordingConnection()
                self.assertIsNone(
                    repository.bind_content_work_unit(
                        conn,
                        plan_id="plan-1",
                        plan_lease_token="plan-lease",
                        target_fingerprint="f" * 64,
                        catalog_build_id="build-1",
                        catalog_item_id=item_id,
                        content_lease_token="content-lease",
                        logical_attempt=1,
                        content_phase="outline",
                        item_work_unit_deadline_at=1_000,
                        now=999,
                    )
                )

                repository.plan["work_unit_kind"] = "provider_phase"
                repository.plan["bound_catalog_item_id"] = item_id
                repository.plan["bound_content_attempt_ordinal"] = 1
                repository.plan["bound_content_phase"] = "outline"
                repository.plan["hard_deadline_at"] = 1_000
                self.assertFalse(
                    repository.heartbeat_bound_content_work_unit(
                        _HeartbeatCasConnection(
                            item_rowcount=1, plan_rowcount=1
                        ),
                        plan_id="plan-1",
                        plan_lease_token="plan-lease",
                        target_fingerprint="f" * 64,
                        catalog_build_id="build-1",
                        catalog_item_id=item_id,
                        content_lease_token="content-lease",
                        logical_attempt=1,
                        content_phase="outline",
                        item_work_unit_deadline_at=1_000,
                        now=999,
                        plan_lease_ms=90_000,
                    )
                )

        host_mutations = {
            **common_mutations,
            "provider_outer_present": {
                "content_provider_attempt_hard_deadline_at": 1_800_100
            },
            "gate_status": {"content_gate_status": "not_started"},
            "gate_ordinal_zero": {"content_gate_attempt_count": 0},
            "gate_ordinal_bool": {"content_gate_attempt_count": True},
        }
        for name, mutation in host_mutations.items():
            with self.subTest(kind="host", drift=name):
                repository = _BoundaryAuthorityRepository()
                repository.plan.update(
                    {
                        "lease_expires_at": 2_000,
                        "hard_deadline_at": 2_000,
                        "work_unit_kind": "coordinator",
                    }
                )
                repository.item.update(
                    {
                        "content_phase": "host_gate_running",
                        "content_gate_status": "pending",
                        "content_gate_attempt_count": 1,
                        "content_provider_attempt_hard_deadline_at": None,
                        **mutation,
                    }
                )
                item_id = str(repository.item["id"])
                self.assertIsNone(
                    repository.bind_content_work_unit(
                        _RecordingConnection(),
                        plan_id="plan-1",
                        plan_lease_token="plan-lease",
                        target_fingerprint="f" * 64,
                        catalog_build_id="build-1",
                        catalog_item_id=item_id,
                        content_lease_token="content-lease",
                        logical_attempt=1,
                        content_phase="host_gate_running",
                        item_work_unit_deadline_at=1_000,
                        now=999,
                    )
                )

        repository = _BoundaryAuthorityRepository()
        item_id = str(repository.item["id"])
        repository.plan.update(
            {
                "lease_expires_at": 2_000,
                "hard_deadline_at": 2_000,
                "work_unit_kind": "coordinator",
            }
        )
        repository._lock_shared_authority = lambda *_args, **_kwargs: (
            {"id": "release-1"},
            {
                "id": "build-1",
                "status": "failed",
                "error_code": "preparation_content_contract_drift",
                "error_message_safe": "failed",
                "completed_at": 999,
            },
            [dict(repository.item)],
            {},
            dict(repository.plan),
        )
        self.assertIsNone(
            repository.bind_content_work_unit(
                _RecordingConnection(),
                plan_id="plan-1",
                plan_lease_token="plan-lease",
                target_fingerprint="f" * 64,
                catalog_build_id="build-1",
                catalog_item_id=item_id,
                content_lease_token="content-lease",
                logical_attempt=1,
                content_phase="outline",
                item_work_unit_deadline_at=1_000,
                now=999,
            )
        )

    def test_all_task7_provider_phases_bind_and_heartbeat_from_frozen_authority(self):
        phases = tuple(str(row["phase"]) for row in QUESTION_PHASE_IO)
        self.assertEqual(len(phases), 14)
        for phase in phases:
            with self.subTest(phase=phase):
                repository = _BoundaryAuthorityRepository()
                item_id = str(repository.item["id"])
                repository.item["content_phase"] = phase
                repository.plan.update(
                    {
                        "lease_expires_at": 2_000,
                        "hard_deadline_at": 2_000,
                        "work_unit_kind": "coordinator",
                    }
                )
                self.assertIsNotNone(
                    repository.bind_content_work_unit(
                        _RecordingConnection(),
                        plan_id="plan-1",
                        plan_lease_token="plan-lease",
                        target_fingerprint="f" * 64,
                        catalog_build_id="build-1",
                        catalog_item_id=item_id,
                        content_lease_token="content-lease",
                        logical_attempt=1,
                        content_phase=phase,
                        item_work_unit_deadline_at=1_000,
                        now=999,
                    )
                )
                repository.plan.update(
                    {
                        "work_unit_kind": "provider_phase",
                        "bound_catalog_item_id": item_id,
                        "bound_content_attempt_ordinal": 1,
                        "bound_content_phase": phase,
                        "hard_deadline_at": 1_000,
                    }
                )
                self.assertTrue(
                    repository.heartbeat_bound_content_work_unit(
                        _HeartbeatCasConnection(
                            item_rowcount=1,
                            plan_rowcount=1,
                        ),
                        plan_id="plan-1",
                        plan_lease_token="plan-lease",
                        target_fingerprint="f" * 64,
                        catalog_build_id="build-1",
                        catalog_item_id=item_id,
                        content_lease_token="content-lease",
                        logical_attempt=1,
                        content_phase=phase,
                        item_work_unit_deadline_at=1_000,
                        now=999,
                        plan_lease_ms=90_000,
                    )
                )

    def test_blocking_provider_and_host_are_jointly_heartbeated_until_return(self):
        for phase, work_kind in (
            ("outline", "provider_phase"),
            ("host_gate_running", "host_gate"),
        ):
            with self.subTest(work_kind=work_kind):
                repository = _HeartbeatRepository()
                catalog = _BlockingClaimCatalog(
                    phase=phase,
                    work_kind=work_kind,
                )
                adapter = CheckpointSharedBuildAdapter(
                    catalog,
                    repository=repository,
                    clock=lambda: 1_000,
                    plan_lease_ms=90_000,
                    heartbeat_interval_ms=10,
                )
                plan = {
                    **_planning_plan(),
                    "stage": "generating_content",
                    "catalog_build_id": "build-1",
                    "catalog_release_id": "release-1",
                }

                result = adapter.advance(
                    plan,
                    now_ms=1_000,
                    heartbeat=lambda: True,
                )

                self.assertEqual(result.result_kind, "progressed")
                self.assertGreaterEqual(repository.heartbeat_calls, 3)
                stopped_count = repository.heartbeat_calls
                threading.Event().wait(0.035)
                self.assertEqual(repository.heartbeat_calls, stopped_count)
                self.assertEqual(len(repository.bound_claims), 1)
                self.assertEqual(repository.reconcile_calls, 1)
                self.assertEqual(repository.release_calls, 1)
                self.assertEqual(
                    repository.reconcile_arguments[0]["owner_plan_id"],
                    "plan-1",
                )
                self.assertEqual(
                    repository.reconcile_arguments[0]["owner_lease_token"],
                    "plan-lease",
                )

    def test_only_handoff_reconcile_receives_exact_owner_cas_identity(self):
        repository = _HeartbeatRepository()
        adapter = CheckpointSharedBuildAdapter(
            _ImmediateCatalogResult("handoff"),
            repository=repository,
            clock=lambda: 1_000,
        )
        plan = {
            **_planning_plan(),
            "stage": "generating_content",
            "catalog_build_id": "build-1",
            "catalog_release_id": "release-1",
        }

        result = adapter.advance(
            plan,
            now_ms=1_000,
            heartbeat=lambda: True,
        )

        self.assertEqual(result.result_kind, "handoff")
        self.assertEqual(repository.reconcile_calls, 1)
        self.assertEqual(
            repository.reconcile_arguments[0]["owner_plan_id"],
            "plan-1",
        )
        self.assertEqual(
            repository.reconcile_arguments[0]["owner_lease_token"],
            "plan-lease",
        )
        self.assertEqual(repository.release_calls, 0)

    def test_handoff_is_stale_when_exact_owner_postcondition_is_missing(self):
        repository = _HeartbeatRepository()
        repository.exact_owner_handoff = False
        adapter = CheckpointSharedBuildAdapter(
            _ImmediateCatalogResult("handoff"),
            repository=repository,
            clock=lambda: 1_000,
        )
        plan = {
            **_planning_plan(),
            "stage": "generating_content",
            "catalog_build_id": "build-1",
            "catalog_release_id": "release-1",
        }

        result = adapter.advance(
            plan,
            now_ms=1_000,
            heartbeat=lambda: True,
        )

        self.assertEqual(result.result_kind, "stale")
        self.assertEqual(result.next_status, "stale")
        self.assertEqual(result.next_stage, "generating_content")
        self.assertEqual(repository.reconcile_calls, 1)
        self.assertEqual(repository.release_calls, 0)

    def test_dependency_retry_skips_full_reconcile_before_narrow_defer(self):
        repository = _HeartbeatRepository()
        adapter = CheckpointSharedBuildAdapter(
            _ImmediateCatalogResult("dependency_retry"),
            repository=repository,
            clock=lambda: 1_000,
        )
        plan = {
            **_planning_plan(),
            "stage": "generating_content",
            "catalog_build_id": "build-1",
            "catalog_release_id": "release-1",
        }

        result = adapter.advance(
            plan,
            now_ms=1_000,
            heartbeat=lambda: True,
        )

        self.assertEqual(result.result_kind, "dependency_retry")
        self.assertEqual(result.next_status, "queued")
        self.assertEqual(result.next_stage, "retry_wait")
        self.assertEqual(repository.reconcile_calls, 0)
        self.assertEqual(repository.defer_calls, 1)
        self.assertEqual(repository.release_calls, 0)

    def test_blocked_heartbeat_guard_must_stop_before_reconcile_or_release(self):
        repository = _BlockedHeartbeatRepository()
        adapter = CheckpointSharedBuildAdapter(
            _ReturnAfterHeartbeatStartsCatalog(repository),
            repository=repository,
            clock=lambda: 1_000,
            plan_lease_ms=90_000,
            heartbeat_interval_ms=1,
        )
        plan = {
            **_planning_plan(),
            "stage": "generating_content",
            "catalog_build_id": "build-1",
            "catalog_release_id": "release-1",
        }
        result = []
        failure = []

        def run_advance():
            try:
                result.append(
                    adapter.advance(plan, now_ms=1_000, heartbeat=lambda: True)
                )
            except BaseException as exc:  # pragma: no cover - asserted below
                failure.append(exc)

        worker = threading.Thread(target=run_advance)
        worker.start()
        self.assertTrue(repository.heartbeat_entered.wait(1))
        try:
            worker.join(1.1)
            self.assertTrue(
                worker.is_alive(),
                "adapter continued while its heartbeat thread was still blocked",
            )
            self.assertEqual(repository.reconcile_calls, 0)
            self.assertEqual(repository.release_calls, 0)
        finally:
            repository.heartbeat_unblock.set()
            worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(failure, [])
        self.assertEqual(len(result), 1)
        self.assertEqual(repository.reconcile_calls, 1)
        self.assertEqual(repository.release_calls, 1)
        stopped_count = repository.heartbeat_calls
        threading.Event().wait(0.02)
        self.assertEqual(repository.heartbeat_calls, stopped_count)
        self.assertFalse(
            any(
                thread.name == "learning-content-joint-heartbeat"
                and thread.is_alive()
                for thread in threading.enumerate()
            )
        )

    def test_repository_exposes_exact_shared_work_authority_surface(self):
        expected = {
            "authorize_shared_build_planning",
            "bind_content_work_unit",
            "reconcile_shared_build",
            "heartbeat_bound_content_work_unit",
            "release_content_continuation",
            "defer_bound_dependency",
            "fail_shared_build_plans",
        }
        self.assertTrue(
            expected.issubset(set(dir(LearningCurriculumPreparationRepository)))
        )
        bind = inspect.signature(
            LearningCurriculumPreparationRepository.bind_content_work_unit
        )
        self.assertEqual(
            set(bind.parameters),
            {
                "self",
                "conn",
                "plan_id",
                "plan_lease_token",
                "target_fingerprint",
                "catalog_build_id",
                "catalog_item_id",
                "content_lease_token",
                "logical_attempt",
                "content_phase",
                "item_work_unit_deadline_at",
                "now",
            },
        )
        constructor = inspect.signature(
            LearningCurriculumPreparationRepository.__init__
        )
        self.assertIn("content_proof_auditor", constructor.parameters)
        self.assertIn("content_dispatch_graph_auditor", constructor.parameters)
        self.assertIn("content_parent_retry_auditor", constructor.parameters)
        reconcile = inspect.signature(
            LearningCurriculumPreparationRepository.reconcile_shared_build
        )
        self.assertEqual(
            set(reconcile.parameters),
            {
                "self",
                "conn",
                "build_id",
                "target_fingerprint",
                "now",
                "owner_plan_id",
                "owner_lease_token",
            },
        )

    def test_handoff_authority_preserves_other_live_owner_and_cas_exact_owner(self):
        classify = LearningCurriculumPreparationRepository._handoff_authority
        base = {"id": "plan-1", "lease_token": None, "lease_expires_at": None}

        self.assertEqual(
            classify(
                base,
                now=1_000,
                owner_plan_id="owner-plan",
                owner_lease_token="owner-lease",
            ),
            "follower",
        )
        self.assertEqual(
            classify(
                {**base, "lease_token": "expired", "lease_expires_at": 1_000},
                now=1_000,
                owner_plan_id="owner-plan",
                owner_lease_token="owner-lease",
            ),
            "follower",
        )
        self.assertEqual(
            classify(
                {**base, "lease_token": "other", "lease_expires_at": 1_001},
                now=1_000,
                owner_plan_id="owner-plan",
                owner_lease_token="owner-lease",
            ),
            "skip",
        )
        self.assertEqual(
            classify(
                {
                    **base,
                    "id": "owner-plan",
                    "lease_token": "owner-lease",
                    "lease_expires_at": 1_001,
                },
                now=1_000,
                owner_plan_id="owner-plan",
                owner_lease_token="owner-lease",
            ),
            "owner",
        )
        self.assertEqual(
            classify(
                {
                    **base,
                    "id": "owner-plan",
                    "lease_token": "changed-lease",
                    "lease_expires_at": 1_001,
                },
                now=1_000,
                owner_plan_id="owner-plan",
                owner_lease_token="owner-lease",
            ),
            "skip",
        )

    def test_live_owner_requires_exact_catalog_pair_while_follower_may_be_unbound(self):
        matches = LearningCurriculumPreparationRepository._catalog_pair_authority_matches
        exact = {
            "catalog_build_id": "catalog-build",
            "catalog_release_id": "catalog-release",
        }
        empty = {"catalog_build_id": None, "catalog_release_id": None}

        self.assertTrue(
            matches(
                exact,
                build_id="catalog-build",
                release_id="catalog-release",
                live_owner=True,
            )
        )
        self.assertFalse(
            matches(
                empty,
                build_id="catalog-build",
                release_id="catalog-release",
                live_owner=True,
            )
        )
        self.assertTrue(
            matches(
                empty,
                build_id="catalog-build",
                release_id="catalog-release",
                live_owner=False,
            )
        )
        self.assertFalse(
            matches(
                {"catalog_build_id": "catalog-build", "catalog_release_id": None},
                build_id="catalog-build",
                release_id="catalog-release",
                live_owner=False,
            )
        )

    def test_content_subject_progress_is_derived_from_sealed_item_ids(self):
        target = build_preparation_target("primary_1")
        items = [
            {"id": f"item-{index}", "subject": subject}
            for subject, total in (
                ("chinese", 12),
                ("math", 9),
                ("english", 9),
            )
            for index in range(
                {
                    "chinese": 0,
                    "math": 12,
                    "english": 21,
                }[subject],
                {
                    "chinese": 0,
                    "math": 12,
                    "english": 21,
                }[subject]
                + total,
            )
        ]
        actual = LearningCurriculumPreparationRepository._content_subject_progress(
            target=target,
            items=items,
            passed_ids=frozenset({"item-0", "item-1", "item-12"}),
            failed_ids=frozenset({"item-21"}),
        )

        self.assertEqual(
            actual,
            {
                "chinese": {
                    "totalCourseCount": 12,
                    "readyCourseCount": 0,
                    "failedCourseCount": 0,
                    "contentCandidateCount": 2,
                    "contentFailedCount": 0,
                },
                "math": {
                    "totalCourseCount": 9,
                    "readyCourseCount": 0,
                    "failedCourseCount": 0,
                    "contentCandidateCount": 1,
                    "contentFailedCount": 0,
                },
                "english": {
                    "totalCourseCount": 9,
                    "readyCourseCount": 0,
                    "failedCourseCount": 0,
                    "contentCandidateCount": 0,
                    "contentFailedCount": 1,
                },
            },
        )

    def test_v2_subject_content_counts_reject_untrusted_shapes_and_types(self):
        target = build_preparation_target("primary_1")
        base = {
            "chinese": {
                "totalCourseCount": 12,
                "readyCourseCount": 0,
                "failedCourseCount": 0,
                "contentCandidateCount": 2,
                "contentFailedCount": 0,
            },
            "math": {
                "totalCourseCount": 9,
                "readyCourseCount": 0,
                "failedCourseCount": 0,
                "contentCandidateCount": 1,
                "contentFailedCount": 0,
            },
            "english": {
                "totalCourseCount": 9,
                "readyCourseCount": 0,
                "failedCourseCount": 0,
                "contentCandidateCount": 0,
                "contentFailedCount": 0,
            },
        }
        plan = {
            "total_course_count": 30,
            "ready_course_count": 0,
            "failed_course_count": 0,
            "content_candidate_count": 3,
            "content_failed_count": 0,
            "target_spec_json": json.dumps(target),
        }
        mutations = {
            "missing": lambda value: value["chinese"].pop(
                "contentCandidateCount"
            ),
            "extra": lambda value: value["chinese"].update(extra=0),
            "bool": lambda value: value["chinese"].update(
                contentCandidateCount=True
            ),
            "string": lambda value: value["chinese"].update(
                contentCandidateCount="2"
            ),
            "negative": lambda value: value["chinese"].update(
                contentCandidateCount=-1
            ),
            "per_subject_overflow": lambda value: value["chinese"].update(
                contentCandidateCount=13
            ),
            "scalar_sum_drift": lambda value: value["chinese"].update(
                contentCandidateCount=1
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                candidate = json.loads(json.dumps(base))
                mutate(candidate)
                with self.assertRaises(ValueError):
                    LearningCurriculumPreparationRepository._validate_progress_counts(
                        plan,
                        ready_course_count=0,
                        failed_course_count=0,
                        subject_progress=candidate,
                        monotonic=False,
                    )

        LearningCurriculumPreparationRepository._validate_progress_counts(
            plan,
            ready_course_count=0,
            failed_course_count=0,
            subject_progress=base,
            monotonic=False,
        )

    def test_planning_uses_only_restricted_content_build_entrypoint(self):
        catalog = _PlanningCatalog()
        repository = _PlanningRepository()
        adapter = CheckpointSharedBuildAdapter(
            catalog,
            repository=repository,
            clock=lambda: 1_001,
        )

        result = adapter.advance(
            _planning_plan(), now_ms=1_000, heartbeat=lambda: True
        )

        self.assertEqual(catalog.restricted_calls, 1)
        self.assertEqual(catalog.public_calls, 0)
        self.assertEqual(catalog.direct_content_calls, 0)
        self.assertEqual(len(repository.authorizations), 1)
        self.assertEqual(len(repository.completed), 1)
        self.assertEqual(len(repository.reconciled), 1)
        self.assertEqual(result.next_stage, "generating_content")
        self.assertTrue(result.already_persisted)

    def test_planning_revalidates_live_authority_before_catalog_create(self):
        catalog = _PlanningCatalog()
        repository = _PlanningRepository(authorized=False)
        adapter = CheckpointSharedBuildAdapter(
            catalog,
            repository=repository,
            clock=lambda: 1_001,
        )

        with self.assertRaisesRegex(
            Exception, "planning authority is stale"
        ):
            adapter.advance(
                _planning_plan(), now_ms=1_000, heartbeat=lambda: True
            )

        self.assertEqual(len(repository.authorizations), 1)
        self.assertEqual(catalog.restricted_calls, 0)
        self.assertEqual(catalog.public_calls, 0)
        self.assertEqual(repository.completed, [])
        self.assertEqual(repository.reconciled, [])

    def test_planning_precreate_authority_requires_exact_target_and_empty_binding(self):
        target = build_preparation_target("primary_1")
        fingerprint = preparation_target_fingerprint(target)
        plan = {
            **_planning_plan(),
            "target_spec_json": json.dumps(
                target, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
            "target_fingerprint": fingerprint,
            "shared_build_request_id": f"grade-build:{fingerprint}",
            "curriculum_version": target["curriculumVersion"],
            "preparation_contract_version": target[
                "preparationContractVersion"
            ],
            "lease_expires_at": 2_000,
            "hard_deadline_at": 2_000,
            "work_unit_kind": "coordinator",
            "catalog_build_id": None,
            "catalog_release_id": None,
            "bound_catalog_item_id": None,
            "bound_content_attempt_ordinal": None,
            "bound_content_phase": None,
            "resume_stage": None,
            "retry_reason_code": None,
            "retry_message_safe": None,
        }
        child = {
            "id": plan["child_id"],
            "family_id": plan["family_id"],
            "grade_code": "primary_1",
            "grade_selection_revision": plan["grade_selection_revision"],
        }
        matches = LearningCurriculumPreparationRepository._planning_authority_matches
        self.assertTrue(
            matches(
                child=child,
                plan=plan,
                plan_lease_token="plan-lease",
                target_fingerprint=fingerprint,
                now=1_000,
            )
        )
        paired = {
            **plan,
            "catalog_build_id": "existing-build",
            "catalog_release_id": "existing-release",
        }
        self.assertTrue(
            matches(
                child=child,
                plan=paired,
                plan_lease_token="plan-lease",
                target_fingerprint=fingerprint,
                now=1_000,
            )
        )
        invalid_target = json.loads(plan["target_spec_json"])
        invalid_target["totalCourseCount"] = 29
        invalid_fingerprint = preparation_target_fingerprint(invalid_target)
        mutations = {
            "noncanonical_target": {
                "target_spec_json": json.dumps(
                    invalid_target,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "target_fingerprint": invalid_fingerprint,
                "shared_build_request_id": f"grade-build:{invalid_fingerprint}",
            },
            "wrong_shared_request": {"shared_build_request_id": "grade-build:wrong"},
            "lease_at_now": {"lease_expires_at": 1_000},
            "deadline_at_now": {"hard_deadline_at": 1_000},
            "bound_item": {"bound_catalog_item_id": "item-1"},
            "bound_attempt": {"bound_content_attempt_ordinal": 1},
            "bound_phase": {"bound_content_phase": "outline"},
            "resume_stage": {"resume_stage": "planning"},
            "retry_code": {"retry_reason_code": "dependency"},
            "retry_message": {"retry_message_safe": "dependency"},
            "build_without_release": {
                "catalog_build_id": "existing-build",
                "catalog_release_id": None,
            },
            "release_without_build": {
                "catalog_build_id": None,
                "catalog_release_id": "existing-release",
            },
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name):
                candidate = {**plan, **mutation}
                candidate_fingerprint = str(candidate["target_fingerprint"])
                self.assertFalse(
                    matches(
                        child=child,
                        plan=candidate,
                        plan_lease_token="plan-lease",
                        target_fingerprint=candidate_fingerprint,
                        now=1_000,
                    )
                )


class LearningCurriculumPreparationSharedBuildMysqlTest(unittest.TestCase):
    def setUp(self):
        config = fresh_test_config()
        self.database_url = config["DATABASE_URL"]
        self.assertIn("/ai_camera_app_test", self.database_url)
        self.assertNotIn("/ai_camera_app_dev", self.database_url)
        self.database = Database(self.database_url)
        with self.database.transaction() as conn:
            for ordinal, revision in ((1, 2), (2, 9)):
                family_id = f"shared_family_{ordinal}"
                child_id = f"shared_child_{ordinal}"
                conn.execute(
                    "INSERT INTO families(id, name, created_at) VALUES (?, ?, 1)",
                    (family_id, family_id),
                )
                conn.execute(
                    """
                    INSERT INTO children(
                      id, family_id, name, created_at, updated_at
                    ) VALUES (?, ?, ?, 1, 1)
                    """,
                    (child_id, family_id, child_id),
                )
                conn.execute(
                    """
                    UPDATE children
                    SET grade_code = 'primary_1',
                      grade_school_year_start = 2026,
                      grade_selection_revision = ?
                    WHERE id = ?
                    """,
                    (revision, child_id),
                )

    def tearDown(self):
        reset_mysql_test_database(self.database_url)

    @staticmethod
    def _profiles():
        return {
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

    def _runtime(self, *, clock, provider=None, host=None, profiles=None):
        staged = (
            StagedContentCandidateGenerator(
                repository=DynamicLearningCourseRepository(self.database),
                adapter=provider,
                clock_ms=clock,
            )
            if provider is not None
            else None
        )
        catalog = LearningCatalogReleaseService(
            self.database_url,
            dynamic_generation_service=None,
            lesson_package_service=None,
            staged_content_candidate_generator=staged,
            primary_one_host_validator=host,
            question_phase_provider_profiles=(
                (profiles or self._profiles())
                if provider is not None and host is not None
                else None
            ),
            clock_ms=clock,
        )
        repository = LearningCurriculumPreparationRepository(
            self.database,
            content_proof_auditor=catalog.audit_locked_content_proofs,
            content_dispatch_graph_auditor=(
                catalog.audit_content_host_retry_graph
            ),
            content_parent_retry_auditor=(
                catalog.audit_content_parent_retry_authority
            ),
            content_provider_dependency_auditor=(
                catalog.audit_content_provider_dependency_retry
            ),
            content_host_dependency_auditor=(
                catalog.audit_content_host_dependency_retry
            ),
        )
        adapter = CheckpointSharedBuildAdapter(
            catalog,
            repository=repository,
            clock=clock,
            plan_lease_ms=90_000,
            heartbeat_interval_ms=15_000,
        )
        runner = LearningCurriculumPreparationRunner(
            repository=repository,
            adapter=adapter,
            clock=clock,
        )
        return catalog, repository, runner

    def _reserve_one(self, repository, *, now=100_000):
        target = build_preparation_target("primary_1")
        fingerprint = preparation_target_fingerprint(target)
        with repository.transaction() as conn:
            plan, _created = repository.reserve_plan(
                conn,
                family_id="shared_family_1",
                child_id="shared_child_1",
                grade_code="primary_1",
                school_year_start_year=2026,
                grade_selection_revision=2,
                target=target,
                target_fingerprint=fingerprint,
                request_id=f"single-plan-{now}",
                shared_build_request_id=f"grade-build:{fingerprint}",
                now=now,
            )
        return plan

    def test_real_planning_drift_stops_before_catalog_create_or_provider(self):
        repository = LearningCurriculumPreparationRepository(self.database)
        target = build_preparation_target("primary_1")
        fingerprint = preparation_target_fingerprint(target)
        now = 90_000
        for ordinal, drift in enumerate(
            ("child_revision", "lease_expiry", "fingerprint"),
            start=10,
        ):
            with self.subTest(drift=drift):
                family_id = f"planning_drift_family_{ordinal}"
                child_id = f"planning_drift_child_{ordinal}"
                with repository.transaction() as conn:
                    conn.execute(
                        "INSERT INTO families(id, name, created_at) VALUES (?, ?, 1)",
                        (family_id, family_id),
                    )
                    conn.execute(
                        """
                        INSERT INTO children(id, family_id, name, created_at, updated_at)
                        VALUES (?, ?, ?, 1, 1)
                        """,
                        (child_id, family_id, child_id),
                    )
                    conn.execute(
                        """
                        UPDATE children
                        SET grade_code = 'primary_1',
                          grade_school_year_start = 2026,
                          grade_selection_revision = 1
                        WHERE id = ?
                        """,
                        (child_id,),
                    )
                    reserved, _created = repository.reserve_plan(
                        conn,
                        family_id=family_id,
                        child_id=child_id,
                        grade_code="primary_1",
                        school_year_start_year=2026,
                        grade_selection_revision=1,
                        target=target,
                        target_fingerprint=fingerprint,
                        request_id=f"task8-planning-drift-{drift}",
                        shared_build_request_id=f"grade-build:{fingerprint}",
                        now=now,
                    )
                    conn.execute(
                        """
                        UPDATE learning_curriculum_preparation_plans
                        SET status = 'running', stage = 'planning',
                          lease_token = 'planning-lease',
                          lease_expires_at = ?, heartbeat_at = ?,
                          hard_deadline_at = ?, work_unit_kind = 'coordinator'
                        WHERE id = ?
                        """,
                        (now + 120_000, now, now + 120_000, reserved["id"]),
                    )
                    claimed = dict(repository.get_plan(conn, str(reserved["id"])))
                with repository.transaction() as conn:
                    if drift == "child_revision":
                        conn.execute(
                            """
                            UPDATE children SET grade_selection_revision = 2
                            WHERE id = ?
                            """,
                            (child_id,),
                        )
                    elif drift == "lease_expiry":
                        conn.execute(
                            """
                            UPDATE learning_curriculum_preparation_plans
                            SET lease_expires_at = ? WHERE id = ?
                            """,
                            (now, reserved["id"]),
                        )
                    else:
                        conn.execute(
                            """
                            UPDATE learning_curriculum_preparation_plans
                            SET target_fingerprint = ? WHERE id = ?
                            """,
                            ("0" * 64, reserved["id"]),
                        )
                catalog = _PlanningCatalog()
                adapter = CheckpointSharedBuildAdapter(
                    catalog,
                    repository=repository,
                    clock=lambda: now,
                )

                with self.assertRaisesRegex(
                    Exception, "planning authority is stale"
                ):
                    adapter.advance(
                        claimed,
                        now_ms=now,
                        heartbeat=lambda: True,
                    )

                self.assertEqual(catalog.restricted_calls, 0)
                self.assertEqual(catalog.public_calls, 0)

    def test_planning_completion_rejects_post_create_manifest_item_drift(self):
        clock = _MutableClock(100_000)
        catalog, repository, _runner = self._runtime(clock=clock)
        reserved = self._reserve_one(repository, now=100_000)
        target = build_preparation_target("primary_1")
        fingerprint = preparation_target_fingerprint(target)
        with repository.transaction() as conn:
            conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET status = 'running', stage = 'planning',
                  lease_token = 'planning-lease', lease_expires_at = 200000,
                  heartbeat_at = 100000, hard_deadline_at = 200000,
                  work_unit_kind = 'coordinator'
                WHERE id = ?
                """,
                (reserved["id"],),
            )
        created = catalog.create_preparation_content_build(
            request_id=f"grade-build:{fingerprint}",
            title="Task 8 planning manifest authority",
            preparation_target=target,
            target_fingerprint=fingerprint,
        )
        build_id = str(created["build"]["id"])
        release_id = str(created["release"]["id"])
        with repository.transaction() as conn:
            conn.execute(
                """
                UPDATE learning_catalog_build_items
                SET skill_id = 'drifted-after-create'
                WHERE build_job_id = ?
                ORDER BY subject_ordinal, boundary_ordinal, variant_ordinal
                LIMIT 1
                """,
                (build_id,),
            )
            completed = repository.complete_shared_build_planning(
                conn,
                plan_id=str(reserved["id"]),
                plan_lease_token="planning-lease",
                target_fingerprint=fingerprint,
                catalog_build_id=build_id,
                catalog_release_id=release_id,
                now=100_000,
                next_run_at=101_000,
            )
            live = repository.get_plan(conn, str(reserved["id"]))

        self.assertFalse(completed)
        self.assertEqual(live["stage"], "planning")
        self.assertEqual(live["lease_token"], "planning-lease")

    def test_reconcile_rechecks_locked_plan_after_hint_to_plan_race(self):
        clock = _MutableClock(100_000)
        _catalog, repository, runner = self._runtime(
            clock=clock,
            provider=_CompletePrimaryOneAdapter(),
            host=_CountingHostValidator(),
        )
        reserved = self._reserve_one(repository, now=100_000)
        self._run_planning(runner, clock)
        target = build_preparation_target("primary_1")
        fingerprint = preparation_target_fingerprint(target)
        with repository.transaction() as conn:
            original = dict(repository.get_plan(conn, str(reserved["id"])))
        build_id = str(original["catalog_build_id"])

        class _MutationProxy:
            def __init__(self, delegate, mutate):
                self.delegate = delegate
                self.mutate = mutate
                self.mutated = False

            def execute(self, sql, params=()):
                normalized = " ".join(sql.split())
                if (
                    not self.mutated
                    and "SELECT * FROM children WHERE id IN" in normalized
                ):
                    self.mutated = True
                    self.mutate()
                return self.delegate.execute(sql, params)

        mutations = {
            "grade_code": {"grade_code": "primary_2"},
            "shared_request": {
                "shared_build_request_id": "grade-build:" + "0" * 64
            },
            "catalog_pair": {
                "catalog_build_id": "catalog_build_raced",
                "catalog_release_id": "catalog_release_raced",
            },
        }
        for label, mutation in mutations.items():
            with self.subTest(race=label):
                assignments = ", ".join(f"{field} = ?" for field in mutation)

                def mutate_plan():
                    with repository.transaction() as second:
                        second.execute(
                            f"""
                            UPDATE learning_curriculum_preparation_plans
                            SET {assignments} WHERE id = ?
                            """,
                            (*mutation.values(), reserved["id"]),
                        )

                with repository.transaction() as conn:
                    proxy = _MutationProxy(conn, mutate_plan)
                    updated = repository.reconcile_shared_build(
                        proxy,
                        build_id=build_id,
                        target_fingerprint=fingerprint,
                        now=102_000,
                    )
                    restore_fields = tuple(mutation)
                    restore_assignments = ", ".join(
                        f"{field} = ?" for field in restore_fields
                    )
                    conn.execute(
                        f"""
                        UPDATE learning_curriculum_preparation_plans
                        SET {restore_assignments} WHERE id = ?
                        """,
                        (
                            *(original[field] for field in restore_fields),
                            reserved["id"],
                        ),
                    )
                self.assertTrue(proxy.mutated)
                self.assertEqual(updated, 0)
        with repository.transaction() as conn:
            conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET curriculum_version = 'drifted-curriculum'
                WHERE id = ?
                """,
                (reserved["id"],),
            )
        with repository.transaction() as conn:
            updated = repository.reconcile_shared_build(
                conn,
                build_id=build_id,
                target_fingerprint=fingerprint,
                now=102_000,
            )
            conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET curriculum_version = ? WHERE id = ?
                """,
                (original["curriculum_version"], reserved["id"]),
            )
        self.assertEqual(updated, 0)

    def test_terminal_fanout_sees_follower_committed_while_waiting_release_mutex(self):
        clock = _MutableClock(100_000)
        catalog, repository, runner = self._runtime(
            clock=clock,
            provider=_CompletePrimaryOneAdapter(),
            host=_CountingHostValidator(),
        )
        first = self._reserve_one(repository)
        self._run_planning(runner, clock)
        target = build_preparation_target("primary_1")
        fingerprint = preparation_target_fingerprint(target)
        with repository.transaction() as conn:
            live_first = repository.get_plan(conn, str(first["id"]))
            build_id = str(live_first["catalog_build_id"])
            release_id = str(live_first["catalog_release_id"])
            catalog.repository.fence_content_failure(
                conn,
                build_id=build_id,
                item_id=None,
                error_code="preparation_content_contract_drift",
                now=102_000,
            )

        reached_release_lock = threading.Event()
        worker_result = []
        worker_errors = []

        class _ReleaseLockObservedConnection:
            def __init__(self, delegate):
                self.delegate = delegate

            def execute(self, sql, params=()):
                normalized = " ".join(sql.split())
                if (
                    "FROM learning_catalog_releases" in normalized
                    and "FOR UPDATE" in normalized
                ):
                    reached_release_lock.set()
                return self.delegate.execute(sql, params)

        def terminalize():
            try:
                with repository.transaction() as worker_conn:
                    worker_result.append(
                        repository.fail_shared_build_plans(
                            _ReleaseLockObservedConnection(worker_conn),
                            build_id=build_id,
                            target_fingerprint=fingerprint,
                            now=103_000,
                        )
                    )
            except Exception as exc:  # pragma: no cover - asserted below
                worker_errors.append(exc)

        with repository.transaction() as mutex_conn:
            mutex_conn.execute(
                "SELECT * FROM learning_catalog_releases "
                "WHERE id = ? LIMIT 1 FOR UPDATE",
                (release_id,),
            ).fetchone()
            worker = threading.Thread(target=terminalize)
            worker.start()
            self.assertTrue(reached_release_lock.wait(2))
            with repository.transaction() as follower_conn:
                follower, _created = repository.reserve_plan(
                    follower_conn,
                    family_id="shared_family_2",
                    child_id="shared_child_2",
                    grade_code="primary_1",
                    school_year_start_year=2026,
                    grade_selection_revision=9,
                    target=target,
                    target_fingerprint=fingerprint,
                    request_id="rr-follower-while-release-locked",
                    shared_build_request_id=f"grade-build:{fingerprint}",
                    now=102_500,
                )
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(worker_errors, [])
        with repository.transaction() as conn:
            live_follower = repository.get_plan(conn, str(follower["id"]))
        self.assertEqual(worker_result, [2])
        self.assertEqual(live_follower["status"], "failed")
        self.assertEqual(live_follower["stage"], "completed")
        self.assertEqual(
            live_follower["error_code"],
            "preparation_content_contract_drift",
        )

    def test_handoff_reconcile_sees_follower_committed_while_waiting_release_mutex(self):
        clock = _MutableClock(100_000)
        _catalog, repository, runner = self._runtime(
            clock=clock,
            provider=_CompletePrimaryOneAdapter(),
            host=_CountingHostValidator(),
        )
        first = self._reserve_one(repository)
        self._run_planning(runner, clock)
        target = build_preparation_target("primary_1")
        fingerprint = preparation_target_fingerprint(target)
        with repository.transaction() as conn:
            live_first = repository.get_plan(conn, str(first["id"]))
            build_id = str(live_first["catalog_build_id"])
            release_id = str(live_first["catalog_release_id"])
            items = list(
                conn.execute(
                    """
                    SELECT id FROM learning_catalog_build_items
                    WHERE build_job_id = ?
                    ORDER BY subject_ordinal, boundary_ordinal,
                      variant_ordinal, id
                    """,
                    (build_id,),
                ).fetchall()
            )
            self.assertEqual(len(items), 30)
            conn.execute(
                """
                UPDATE learning_catalog_build_items
                SET status = 'course_ready', attempt_count = 1,
                  active_generation_request_id = generation_request_id,
                  course_id = CONCAT('task8_rr_', id), course_version = 1,
                  content_phase = 'course_ready',
                  content_gate_status = 'passed',
                  content_gate_attempt_count = 1,
                  content_gate_passed_at = 102000,
                  content_validation_contract_version = 'task8-rr-v1',
                  content_receipt_hash = ?,
                  content_claim_attempt_ordinal = 1,
                  content_provider_attempt_hard_deadline_at = NULL,
                  content_work_unit_deadline_at = NULL,
                  updated_at = 102000
                WHERE build_job_id = ?
                """,
                ("a" * 64, build_id),
            )
        passed_item_ids = tuple(str(item["id"]) for item in items)
        reconciliation_repository = LearningCurriculumPreparationRepository(
            self.database,
            content_proof_auditor=lambda _conn, *, build_id: (
                ContentProofAuditSnapshot(
                    build_id=build_id,
                    release_id=release_id,
                    passed_item_ids=passed_item_ids,
                    repairable_item_ids=(),
                    terminal_failed_item_ids=(),
                )
            ),
        )
        reached_release_lock = threading.Event()
        worker_result = []
        worker_errors = []

        class _ReleaseLockObservedConnection:
            def __init__(self, delegate):
                self.delegate = delegate

            def execute(self, sql, params=()):
                normalized = " ".join(sql.split())
                if (
                    "FROM learning_catalog_releases" in normalized
                    and "FOR UPDATE" in normalized
                ):
                    reached_release_lock.set()
                return self.delegate.execute(sql, params)

        def handoff():
            try:
                with reconciliation_repository.transaction() as worker_conn:
                    worker_result.append(
                        reconciliation_repository.reconcile_shared_build(
                            _ReleaseLockObservedConnection(worker_conn),
                            build_id=build_id,
                            target_fingerprint=fingerprint,
                            now=103_000,
                        )
                    )
            except Exception as exc:  # pragma: no cover - asserted below
                worker_errors.append(exc)

        with repository.transaction() as mutex_conn:
            mutex_conn.execute(
                "SELECT * FROM learning_catalog_releases "
                "WHERE id = ? LIMIT 1 FOR UPDATE",
                (release_id,),
            ).fetchone()
            worker = threading.Thread(target=handoff)
            worker.start()
            self.assertTrue(reached_release_lock.wait(2))
            with repository.transaction() as follower_conn:
                follower, _created = repository.reserve_plan(
                    follower_conn,
                    family_id="shared_family_2",
                    child_id="shared_child_2",
                    grade_code="primary_1",
                    school_year_start_year=2026,
                    grade_selection_revision=9,
                    target=target,
                    target_fingerprint=fingerprint,
                    request_id="rr-handoff-follower-while-release-locked",
                    shared_build_request_id=f"grade-build:{fingerprint}",
                    now=102_500,
                )
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(worker_errors, [])
        with repository.transaction() as conn:
            live_first = repository.get_plan(conn, str(first["id"]))
            live_follower = repository.get_plan(conn, str(follower["id"]))
        self.assertEqual(worker_result, [2])
        for plan in (live_first, live_follower):
            self.assertEqual(plan["status"], "running")
            self.assertEqual(plan["stage"], "building_classrooms")
            self.assertEqual(plan["content_candidate_count"], 30)
            self.assertEqual(plan["content_canary_candidate_count"], 3)
            self.assertEqual(plan["progress_percent"], 35)

    @staticmethod
    def _run_planning(runner, clock):
        clock.value = 101_000
        failures = []
        original_advance = runner.adapter.advance

        def traced_advance(*args, **kwargs):
            try:
                return original_advance(*args, **kwargs)
            except Exception as exc:
                failures.append(exc)
                raise

        with patch.object(runner.adapter, "advance", side_effect=traced_advance):
            result = runner.run_once(_runner_app(), now_ms=clock.value)
        if result.get("resultCode") != "progressed":
            if failures:
                raise failures[0]
            raise AssertionError(result)
        return result

    def test_fresh_and_retry_coordinator_dependency_keep_one_deadline(self):
        clock = _MutableClock(100_000)
        _catalog, repository, runner = self._runtime(clock=clock)
        reserved = self._reserve_one(repository)
        self._run_planning(runner, clock)

        clock.value = 102_000
        first = runner.run_once(_runner_app(), now_ms=clock.value)
        with repository.transaction() as conn:
            first_plan = repository.get_plan(conn, str(reserved["id"]))

        self.assertEqual(first["status"], "queued", first)
        self.assertEqual(first["stage"], "retry_wait", first)
        self.assertEqual(first_plan["status"], "queued")
        self.assertEqual(first_plan["stage"], "retry_wait")
        self.assertEqual(first_plan["resume_stage"], "generating_content")
        self.assertEqual(first_plan["work_unit_kind"], "coordinator")
        self.assertEqual(first_plan["hard_deadline_at"], 222_000)
        self.assertIsNone(first_plan["bound_catalog_item_id"])
        self.assertEqual(
            first_plan["retry_reason_code"],
            "preparation_dependency_unavailable",
        )

        clock.value = int(first_plan["next_run_at"])
        second = runner.run_once(_runner_app(), now_ms=clock.value)
        with repository.transaction() as conn:
            second_plan = repository.get_plan(conn, str(reserved["id"]))
        self.assertEqual(second["status"], "queued", second)
        self.assertEqual(second_plan["hard_deadline_at"], 222_000)
        self.assertEqual(second_plan["work_unit_kind"], "coordinator")
        self.assertIsNone(second_plan["bound_catalog_item_id"])

        clock.value = 222_000
        terminal = runner.run_once(_runner_app(), now_ms=clock.value)
        with repository.transaction() as conn:
            terminal_plan = repository.get_plan(conn, str(reserved["id"]))
        self.assertEqual(terminal["status"], "failed", terminal)
        self.assertEqual(
            terminal["errorCode"], "preparation_stage_deadline_exceeded"
        )
        self.assertEqual(terminal_plan["stage"], "completed")
        self.assertIsNone(terminal_plan["hard_deadline_at"])
        self.assertIsNone(terminal_plan["work_unit_kind"])
        self.assertIsNone(terminal_plan["retry_reason_code"])

    def test_factory_missing_profile_configuration_has_zero_ledger_and_process(self):
        from services import service_factory

        now = system_now_ms()
        app = _runner_app()
        app.config.update(
            DATABASE_URL=self.database_url,
            AI_PROVIDER="",
            AI_MODEL="",
            AI_BASE_URL="",
        )
        with app.app_context(), patch.dict(
            os.environ, {"APP_AI_API_KEY": ""}, clear=False
        ):
            adapter = (
                service_factory.learning_curriculum_preparation_checkpoint_adapter()
            )
            public_repository = (
                service_factory.learning_curriculum_preparation_repository()
            )
            self.assertIsNot(public_repository, adapter.repository)
            self.assertIsNone(public_repository.content_proof_auditor)
            repository = adapter.repository
            self.assertIsNone(
                adapter.catalog_service.staged_content_candidate_generator
            )
            target = build_preparation_target("primary_1")
            fingerprint = preparation_target_fingerprint(target)
            with repository.transaction() as conn:
                plan, _created = repository.reserve_plan(
                    conn,
                    family_id="shared_family_1",
                    child_id="shared_child_1",
                    grade_code="primary_1",
                    school_year_start_year=2026,
                    grade_selection_revision=2,
                    target=target,
                    target_fingerprint=fingerprint,
                    request_id="task8-factory-missing-profile",
                    shared_build_request_id=f"grade-build:{fingerprint}",
                    now=now,
                )
            runner = LearningCurriculumPreparationRunner(
                repository=repository,
                adapter=adapter,
            )
            planning = runner.run_once(app, now_ms=now)
            self.assertEqual(planning["resultCode"], "progressed", planning)
            dependency = runner.run_once(app, now_ms=now + 2_000)

        self.assertEqual(dependency["status"], "queued", dependency)
        self.assertEqual(dependency["stage"], "retry_wait", dependency)
        with repository.transaction() as conn:
            current = repository.get_plan(conn, str(plan["id"]))
            dispatches = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM learning_course_provider_dispatches
                """
            ).fetchone()["count"]
            jobs = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM learning_course_generation_jobs
                """
            ).fetchone()["count"]
        self.assertEqual(current["work_unit_kind"], "coordinator")
        self.assertIsNone(current["bound_catalog_item_id"])
        self.assertEqual(dispatches, 0)
        self.assertEqual(jobs, 0)

    def test_missing_provider_key_retries_bound_item_without_spend_or_extension(self):
        clock = _MutableClock(100_000)
        provider = _OutlineOnlyAdapter()
        _catalog, repository, runner = self._runtime(
            clock=clock,
            provider=provider,
            host=LearningGeneratedCourseValidator(),
        )
        reserved = self._reserve_one(repository)
        self._run_planning(runner, clock)

        with patch.dict(os.environ, {"APP_AI_API_KEY": ""}, clear=False):
            clock.value = 102_000
            first = runner.run_once(_runner_app(), now_ms=clock.value)
            with repository.transaction() as conn:
                first_plan = repository.get_plan(conn, str(reserved["id"]))
                first_item = conn.execute(
                    """
                    SELECT * FROM learning_catalog_build_items
                    WHERE id = ? LIMIT 1
                    """,
                    (first_plan["bound_catalog_item_id"],),
                ).fetchone()
                first_dispatches = conn.execute(
                    "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches"
                ).fetchone()["count"]

            self.assertEqual(first["status"], "queued", first)
            self.assertEqual(first["stage"], "retry_wait", first)
            self.assertEqual(first_plan["work_unit_kind"], "provider_phase")
            self.assertEqual(first_plan["bound_content_attempt_ordinal"], 1)
            self.assertEqual(first_plan["bound_content_phase"], "outline")
            self.assertEqual(first_plan["hard_deadline_at"], 222_000)
            self.assertEqual(
                first_item["content_work_unit_deadline_at"],
                first_plan["hard_deadline_at"],
            )
            self.assertIsNone(first_item["content_lease_token"])
            self.assertEqual(first_dispatches, 0)
            self.assertEqual(provider.execute_calls, 0)

            first_identity = (
                first_plan["bound_catalog_item_id"],
                first_plan["bound_content_attempt_ordinal"],
                first_plan["bound_content_phase"],
                first_plan["hard_deadline_at"],
            )
            clock.value = int(first_plan["next_run_at"])
            second = runner.run_once(_runner_app(), now_ms=clock.value)
            with repository.transaction() as conn:
                second_plan = repository.get_plan(conn, str(reserved["id"]))
                second_dispatches = conn.execute(
                    "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches"
                ).fetchone()["count"]
            self.assertEqual(second["status"], "queued", second)
            self.assertEqual(
                (
                    second_plan["bound_catalog_item_id"],
                    second_plan["bound_content_attempt_ordinal"],
                    second_plan["bound_content_phase"],
                    second_plan["hard_deadline_at"],
                ),
                first_identity,
            )
            self.assertEqual(second_dispatches, 0)
            self.assertEqual(provider.execute_calls, 0)

            clock.value = 222_000
            terminal = runner.run_once(_runner_app(), now_ms=clock.value)

        with repository.transaction() as conn:
            terminal_plan = repository.get_plan(conn, str(reserved["id"]))
            terminal_dispatches = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches"
            ).fetchone()["count"]
        self.assertEqual(terminal["status"], "failed", terminal)
        self.assertEqual(
            terminal["errorCode"], "preparation_stage_deadline_exceeded"
        )
        self.assertEqual(terminal_plan["stage"], "completed")
        self.assertIsNone(terminal_plan["hard_deadline_at"])
        self.assertIsNone(terminal_plan["bound_catalog_item_id"])
        self.assertEqual(terminal_dispatches, 0)
        self.assertEqual(provider.execute_calls, 0)

    def test_provider_dependency_release_to_defer_reclaim_race_is_stale(self):
        clock = _MutableClock(100_000)
        provider = _OutlineOnlyAdapter()
        _catalog, repository, runner = self._runtime(
            clock=clock,
            provider=provider,
            host=LearningGeneratedCourseValidator(),
        )
        reserved = self._reserve_one(repository)
        self._run_planning(runner, clock)
        original_defer = repository.defer_bound_dependency
        race = {"ran": False}

        def reclaim_before_defer(conn, **kwargs):
            with self.database.transaction() as race_conn:
                live = repository.get_plan(race_conn, str(reserved["id"]))
                item_id = str(live["bound_catalog_item_id"])
                deadline = int(live["hard_deadline_at"])
                cursor = race_conn.execute(
                    """
                    UPDATE learning_catalog_build_items
                    SET content_lease_token = 'provider-race-lease',
                      content_lease_expires_at = ?, content_heartbeat_at = ?,
                      updated_at = ?
                    WHERE id = ? AND content_lease_token IS NULL
                    """,
                    (deadline, clock.value, clock.value, item_id),
                )
                self.assertEqual(cursor.rowcount, 1)
            race["ran"] = True
            return original_defer(conn, **kwargs)

        with patch.dict(os.environ, {"APP_AI_API_KEY": ""}, clear=False), patch.object(
            repository,
            "defer_bound_dependency",
            side_effect=reclaim_before_defer,
        ):
            clock.value = 102_000
            result = runner.run_once(_runner_app(), now_ms=clock.value)

        with repository.transaction() as conn:
            live = repository.get_plan(conn, str(reserved["id"]))
            item = conn.execute(
                "SELECT * FROM learning_catalog_build_items WHERE id = ? LIMIT 1",
                (live["bound_catalog_item_id"],),
            ).fetchone()
        self.assertTrue(race["ran"])
        self.assertEqual(result["status"], "stale", result)
        self.assertEqual(live["status"], "running")
        self.assertEqual(live["stage"], "generating_content")
        self.assertEqual(item["content_lease_token"], "provider-race-lease")
        self.assertEqual(provider.execute_calls, 0)

    def test_provider_dependency_release_to_defer_future_dispatch_is_stale(self):
        clock = _MutableClock(100_000)
        provider = _OutlineOnlyAdapter()
        _catalog, repository, runner = self._runtime(
            clock=clock,
            provider=provider,
            host=LearningGeneratedCourseValidator(),
        )
        reserved = self._reserve_one(repository)
        self._run_planning(runner, clock)
        with patch.dict(os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False):
            clock.value = 102_000
            first = runner.run_once(_runner_app(), now_ms=clock.value)
        self.assertEqual(first["resultCode"], "progressed", first)
        self.assertEqual(provider.execute_calls, 1)

        original_defer = repository.defer_bound_dependency
        race = {"ran": False}

        def insert_future_dispatch_before_defer(conn, **kwargs):
            with self.database.transaction() as race_conn:
                live = repository.get_plan(race_conn, str(reserved["id"]))
                item_id = str(live["bound_catalog_item_id"])
                source = race_conn.execute(
                    """
                    SELECT * FROM learning_course_provider_dispatches
                    WHERE build_item_id = ? ORDER BY phase_ordinal LIMIT 1
                    """,
                    (item_id,),
                ).fetchone()
                cursor = race_conn.execute(
                    """
                    INSERT INTO learning_course_provider_dispatches(
                      id, build_item_id, logical_attempt, phase, phase_ordinal,
                      generation_request_id, item_lease_token, provider, model,
                      profile, input_sha256, status, checkpoint_json,
                      output_sha256, attempt_started_at,
                      attempt_hard_deadline_at, provider_request_id_hash,
                      input_tokens, output_tokens, billing_evidence,
                      safe_error_code, dispatched_at, completed_at
                    )
                    SELECT 'task8-provider-future-race', build_item_id,
                      logical_attempt, 'verification_after_repair', 14,
                      generation_request_id, item_lease_token, provider, model,
                      profile, input_sha256, status, checkpoint_json,
                      output_sha256, attempt_started_at,
                      attempt_hard_deadline_at, provider_request_id_hash,
                      input_tokens, output_tokens, billing_evidence,
                      safe_error_code, dispatched_at, completed_at
                    FROM learning_course_provider_dispatches WHERE id = ?
                    """,
                    (source["id"],),
                )
                self.assertEqual(cursor.rowcount, 1)
            race["ran"] = True
            return original_defer(conn, **kwargs)

        with patch.dict(os.environ, {"APP_AI_API_KEY": ""}, clear=False), patch.object(
            repository,
            "defer_bound_dependency",
            side_effect=insert_future_dispatch_before_defer,
        ):
            clock.value = 104_000
            result = runner.run_once(_runner_app(), now_ms=clock.value)

        with repository.transaction() as conn:
            live = repository.get_plan(conn, str(reserved["id"]))
        self.assertTrue(race["ran"])
        self.assertEqual(result["status"], "stale", result)
        self.assertEqual(live["status"], "running")
        self.assertEqual(live["stage"], "generating_content")
        self.assertEqual(provider.execute_calls, 1)

    def test_coordinator_dependency_refuses_existing_catalog_work_residue(self):
        clock = _MutableClock(100_000)
        provider = _CompletePrimaryOneAdapter()
        _catalog, repository, runner = self._runtime(
            clock=clock,
            provider=provider,
            host=_CountingHostValidator(),
        )
        reserved = self._reserve_one(repository)
        self._run_planning(runner, clock)
        with patch.dict(os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False):
            clock.value = 102_000
            progressed = runner.run_once(_runner_app(), now_ms=clock.value)
        self.assertEqual(progressed["resultCode"], "progressed", progressed)
        before_provider = provider.execute_calls
        dependency_catalog = LearningCatalogReleaseService(
            self.database_url,
            dynamic_generation_service=None,
            lesson_package_service=None,
            clock_ms=clock,
        )
        dependency_runner = LearningCurriculumPreparationRunner(
            repository=repository,
            adapter=CheckpointSharedBuildAdapter(
                dependency_catalog,
                repository=repository,
                clock=clock,
            ),
            clock=clock,
        )
        clock.value = 104_000
        dependency = dependency_runner.run_once(
            _runner_app(), now_ms=clock.value
        )
        with repository.transaction() as conn:
            live = repository.get_plan(conn, str(reserved["id"]))
            dispatches = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches"
            ).fetchone()["count"]
        self.assertEqual(dependency["status"], "stale", dependency)
        self.assertEqual(live["status"], "running")
        self.assertEqual(live["stage"], "generating_content")
        self.assertEqual(live["work_unit_kind"], "coordinator")
        self.assertEqual(dispatches, 1)
        self.assertEqual(provider.execute_calls, before_provider)

    def test_coordinator_dependency_refuses_other_claim_without_dispatch(self):
        clock = _MutableClock(100_000)
        catalog, repository, runner = self._runtime(
            clock=clock,
            provider=_CompletePrimaryOneAdapter(),
            host=_CountingHostValidator(),
        )
        reserved = self._reserve_one(repository)
        self._run_planning(runner, clock)
        original_defer = repository.defer_bound_dependency
        race = {"ran": False, "itemId": None}

        def claim_without_dispatch(conn, **kwargs):
            with self.database.transaction() as race_conn:
                live = repository.get_plan(race_conn, str(reserved["id"]))
                action = catalog.repository.prepare_content_advance(
                    race_conn,
                    build_id=str(live["catalog_build_id"]),
                    now=clock.value,
                    passed_item_ids=frozenset(),
                    repairable_item_ids=frozenset(),
                    locked_attempt_histories_by_item={},
                )
                self.assertEqual(action["action"], "provider", action)
                race["itemId"] = str(action["item"]["id"])
            race["ran"] = True
            return original_defer(conn, **kwargs)

        dependency_catalog = LearningCatalogReleaseService(
            self.database_url,
            dynamic_generation_service=None,
            lesson_package_service=None,
            clock_ms=clock,
        )
        dependency_runner = LearningCurriculumPreparationRunner(
            repository=repository,
            adapter=CheckpointSharedBuildAdapter(
                dependency_catalog,
                repository=repository,
                clock=clock,
            ),
            clock=clock,
        )
        with patch.object(
            repository,
            "defer_bound_dependency",
            side_effect=claim_without_dispatch,
        ):
            clock.value = 102_000
            result = dependency_runner.run_once(_runner_app(), now_ms=clock.value)

        with repository.transaction() as conn:
            live = repository.get_plan(conn, str(reserved["id"]))
            item = conn.execute(
                "SELECT * FROM learning_catalog_build_items "
                "WHERE id = ? LIMIT 1",
                (race["itemId"],),
            ).fetchone()
            dispatch_count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches"
            ).fetchone()["count"]
        self.assertTrue(race["ran"])
        self.assertEqual(result["status"], "stale", result)
        self.assertEqual(live["status"], "running")
        self.assertEqual(live["stage"], "generating_content")
        self.assertEqual(item["status"], "processing")
        self.assertIsNotNone(item["content_lease_token"])
        self.assertEqual(dispatch_count, 0)

    def test_host_dependency_retries_same_live_ordinal_token_and_deadline(self):
        clock = _MutableClock(100_000)
        provider = _CompletePinyinCanaryAdapter()
        host = _HostDependencyValidator()
        _catalog, repository, runner = self._runtime(
            clock=clock,
            provider=provider,
            host=host,
        )
        reserved = self._reserve_one(repository)
        self._run_planning(runner, clock)

        with patch.dict(os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False):
            for _ in range(6):
                clock.value += 2_000
                progressed = runner.run_once(_runner_app(), now_ms=clock.value)
                self.assertEqual(progressed["resultCode"], "progressed", progressed)

            clock.value += 2_000
            first = runner.run_once(_runner_app(), now_ms=clock.value)
            with repository.transaction() as conn:
                first_plan = repository.get_plan(conn, str(reserved["id"]))
                first_item = conn.execute(
                    """
                    SELECT * FROM learning_catalog_build_items
                    WHERE id = ? LIMIT 1
                    """,
                    (first_plan["bound_catalog_item_id"],),
                ).fetchone()
            self.assertEqual(first["status"], "queued", first)
            self.assertEqual(first["stage"], "retry_wait", first)
            self.assertEqual(first_plan["work_unit_kind"], "host_gate")
            self.assertEqual(first_plan["bound_content_phase"], "host_gate_running")
            self.assertEqual(first_item["content_gate_status"], "retry_wait")
            self.assertEqual(first_item["content_phase"], "host_gate_running")
            self.assertEqual(first_item["content_gate_attempt_count"], 1)
            self.assertIsNotNone(first_item["content_lease_token"])
            self.assertEqual(
                first_plan["hard_deadline_at"],
                first_item["content_work_unit_deadline_at"],
            )
            first_identity = (
                first_plan["bound_catalog_item_id"],
                first_plan["bound_content_attempt_ordinal"],
                first_plan["bound_content_phase"],
                first_plan["hard_deadline_at"],
                first_item["content_gate_attempt_count"],
                first_item["content_lease_token"],
            )

            clock.value = int(first_plan["next_run_at"])
            second = runner.run_once(_runner_app(), now_ms=clock.value)
            with repository.transaction() as conn:
                second_plan = repository.get_plan(conn, str(reserved["id"]))
                second_item = conn.execute(
                    """
                    SELECT * FROM learning_catalog_build_items
                    WHERE id = ? LIMIT 1
                    """,
                    (second_plan["bound_catalog_item_id"],),
                ).fetchone()
            self.assertEqual(second["status"], "queued", second)
            self.assertEqual(
                (
                    second_plan["bound_catalog_item_id"],
                    second_plan["bound_content_attempt_ordinal"],
                    second_plan["bound_content_phase"],
                    second_plan["hard_deadline_at"],
                    second_item["content_gate_attempt_count"],
                    second_item["content_lease_token"],
                ),
                first_identity,
            )
            self.assertEqual(provider.execute_calls, 6)
            self.assertEqual(host.host_calls, 2)

            clock.value = int(first_plan["hard_deadline_at"])
            terminal = runner.run_once(_runner_app(), now_ms=clock.value)

        with repository.transaction() as conn:
            terminal_plan = repository.get_plan(conn, str(reserved["id"]))
            dispatch_count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches"
            ).fetchone()["count"]
        self.assertEqual(terminal["status"], "failed", terminal)
        self.assertEqual(
            terminal["errorCode"], "preparation_stage_deadline_exceeded"
        )
        self.assertEqual(terminal_plan["stage"], "completed")
        self.assertEqual(dispatch_count, 6)
        self.assertEqual(provider.execute_calls, 6)
        self.assertEqual(host.host_calls, 2)

    def test_host_dependency_release_to_defer_token_race_is_stale(self):
        clock = _MutableClock(100_000)
        provider = _CompletePinyinCanaryAdapter()
        host = _HostDependencyValidator()
        _catalog, repository, runner = self._runtime(
            clock=clock,
            provider=provider,
            host=host,
        )
        reserved = self._reserve_one(repository)
        self._run_planning(runner, clock)

        with patch.dict(os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False):
            for _ in range(6):
                clock.value += 2_000
                progressed = runner.run_once(_runner_app(), now_ms=clock.value)
                self.assertEqual(progressed["resultCode"], "progressed", progressed)

            original_defer = repository.defer_bound_dependency
            race = {"ran": False, "original_token": None}

            def rotate_token_before_defer(conn, **kwargs):
                with self.database.transaction() as race_conn:
                    live = repository.get_plan(race_conn, str(reserved["id"]))
                    item_id = str(live["bound_catalog_item_id"])
                    item = race_conn.execute(
                        """
                        SELECT * FROM learning_catalog_build_items
                        WHERE id = ? LIMIT 1
                        """,
                        (item_id,),
                    ).fetchone()
                    race["original_token"] = item["content_lease_token"]
                    cursor = race_conn.execute(
                        """
                        UPDATE learning_catalog_build_items
                        SET content_lease_token = 'host-race-lease', updated_at = ?
                        WHERE id = ? AND content_lease_token = ?
                        """,
                        (clock.value, item_id, item["content_lease_token"]),
                    )
                    self.assertEqual(cursor.rowcount, 1)
                race["ran"] = True
                return original_defer(conn, **kwargs)

            with patch.object(
                repository,
                "defer_bound_dependency",
                side_effect=rotate_token_before_defer,
            ):
                clock.value += 2_000
                result = runner.run_once(_runner_app(), now_ms=clock.value)

        with repository.transaction() as conn:
            live = repository.get_plan(conn, str(reserved["id"]))
            item = conn.execute(
                "SELECT * FROM learning_catalog_build_items WHERE id = ? LIMIT 1",
                (live["bound_catalog_item_id"],),
            ).fetchone()
        self.assertTrue(race["ran"])
        self.assertNotEqual(race["original_token"], "host-race-lease")
        self.assertEqual(result["status"], "stale", result)
        self.assertEqual(live["status"], "running")
        self.assertEqual(live["stage"], "generating_content")
        self.assertEqual(item["content_lease_token"], "host-race-lease")

    def test_attempt_two_uses_real_plan_control_authority_before_claim(self):
        clock = _MutableClock(100_000)
        provider = _RejectingPinyinCanaryAdapter()
        _catalog, repository, runner = self._runtime(
            clock=clock,
            provider=provider,
            host=LearningGeneratedCourseValidator(),
        )
        reserved = self._reserve_one(repository)
        self._run_planning(runner, clock)

        with patch.dict(
            os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False
        ):
            for _ in range(7):
                clock.value += 2_000
                result = runner.run_once(_runner_app(), now_ms=clock.value)
                self.assertEqual(result["resultCode"], "progressed", result)
            with repository.transaction() as conn:
                attempt_one = conn.execute(
                    """
                    SELECT * FROM learning_catalog_build_items
                    WHERE build_job_id = (
                      SELECT catalog_build_id
                      FROM learning_curriculum_preparation_plans
                      WHERE id = ?
                    )
                    ORDER BY subject_ordinal, boundary_ordinal,
                      variant_ordinal, id
                    LIMIT 1
                    """,
                    (reserved["id"],),
                ).fetchone()
            self.assertEqual(attempt_one["attempt_count"], 1)
            self.assertEqual(attempt_one["status"], "failed")
            self.assertEqual(
                attempt_one["content_gate_status"], "failed_deterministic"
            )

            with patch.object(
                repository,
                "authorize_content_control_work",
                wraps=repository.authorize_content_control_work,
            ) as authorize:
                clock.value += 2_000
                attempt_two = runner.run_once(
                    _runner_app(), now_ms=clock.value
                )

        self.assertEqual(attempt_two["resultCode"], "progressed", attempt_two)
        self.assertEqual(authorize.call_count, 1)
        with repository.transaction() as conn:
            item = conn.execute(
                """
                SELECT * FROM learning_catalog_build_items
                WHERE id = ? LIMIT 1
                """,
                (attempt_one["id"],),
            ).fetchone()
            plan = repository.get_plan(conn, str(reserved["id"]))
            attempt_two_dispatches = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM learning_course_provider_dispatches
                WHERE build_item_id = ? AND logical_attempt = 2
                """,
                (attempt_one["id"],),
            ).fetchone()["count"]
        self.assertEqual(item["attempt_count"], 2)
        self.assertEqual(item["status"], "processing")
        self.assertEqual(item["content_phase"], "outline")
        self.assertEqual(attempt_two_dispatches, 0)
        self.assertEqual(plan["status"], "running")
        self.assertEqual(plan["stage"], "generating_content")
        self.assertIsNone(plan["lease_token"])

    def _assert_catalog_commit_crash_recovers_without_duplicate_phase(self, mode):
        clock = _MutableClock(100_000)
        provider = _CompletePinyinCanaryAdapter()
        staged = StagedContentCandidateGenerator(
            repository=DynamicLearningCourseRepository(self.database),
            adapter=provider,
            clock_ms=clock,
        )
        catalog = LearningCatalogReleaseService(
            self.database_url,
            dynamic_generation_service=None,
            lesson_package_service=None,
            staged_content_candidate_generator=staged,
            primary_one_host_validator=LearningGeneratedCourseValidator(),
            question_phase_provider_profiles=self._profiles(),
            clock_ms=clock,
        )
        repository = _CrashWindowRepository(
            self.database,
            content_proof_auditor=catalog.audit_locked_content_proofs,
            content_provider_dependency_auditor=(
                catalog.audit_content_provider_dependency_retry
            ),
        )
        adapter = CheckpointSharedBuildAdapter(
            catalog,
            repository=repository,
            clock=clock,
            plan_lease_ms=90_000,
            heartbeat_interval_ms=15_000,
        )
        runner = LearningCurriculumPreparationRunner(
            repository=repository,
            adapter=adapter,
            clock=clock,
        )
        reserved = self._reserve_one(repository)
        self._run_planning(runner, clock)
        repository.arm(mode)

        with patch.dict(os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False):
            clock.value = 102_000
            with self.assertRaises(_SimulatedProcessCrash):
                runner.run_once(_runner_app(), now_ms=clock.value)

            with repository.transaction() as conn:
                crashed_plan = repository.get_plan(conn, str(reserved["id"]))
                first_dispatches = [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT * FROM learning_course_provider_dispatches
                        ORDER BY phase_ordinal, id
                        """
                    ).fetchall()
                ]
                crashed_item = conn.execute(
                    """
                    SELECT * FROM learning_catalog_build_items
                    WHERE id = ? LIMIT 1
                    """,
                    (crashed_plan["bound_catalog_item_id"],),
                ).fetchone()
            self.assertTrue(repository.crashed)
            self.assertEqual(len(first_dispatches), 1)
            self.assertEqual(first_dispatches[0]["phase"], "outline")
            self.assertEqual(first_dispatches[0]["status"], "succeeded")
            self.assertEqual(crashed_item["content_phase"], "raw_candidate")
            self.assertEqual(crashed_plan["work_unit_kind"], "provider_phase")
            self.assertEqual(crashed_plan["bound_content_phase"], "outline")
            self.assertEqual(crashed_plan["hard_deadline_at"], 222_000)

            clock.value = int(crashed_plan["lease_expires_at"])
            recovered = runner.run_once(_runner_app(), now_ms=clock.value)

        self.assertEqual(recovered["resultCode"], "progressed", recovered)
        with repository.transaction() as conn:
            recovered_plan = repository.get_plan(conn, str(reserved["id"]))
            dispatches = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT * FROM learning_course_provider_dispatches
                    ORDER BY phase_ordinal, id
                    """
                ).fetchall()
            ]
        self.assertEqual([row["phase"] for row in dispatches], ["outline", "raw_candidate"])
        self.assertEqual(len({row["id"] for row in dispatches}), 2)
        self.assertEqual(
            len({row["attempt_hard_deadline_at"] for row in dispatches}),
            1,
        )
        self.assertEqual(provider.execute_calls, 2)
        self.assertEqual(recovered_plan["status"], "running")
        self.assertEqual(recovered_plan["stage"], "generating_content")
        self.assertIsNone(recovered_plan["lease_token"])
        self.assertIsNone(recovered_plan["hard_deadline_at"])
        self.assertIsNone(recovered_plan["bound_catalog_item_id"])

    def test_crash_after_catalog_cas_before_reconcile_recovers_once(self):
        self._assert_catalog_commit_crash_recovers_without_duplicate_phase(
            "before_reconcile"
        )

    def test_crash_after_reconcile_before_owner_release_recovers_once(self):
        self._assert_catalog_commit_crash_recovers_without_duplicate_phase(
            "before_release"
        )

    def test_connection_reset_after_catalog_cas_recovers_without_retry_wait(self):
        clock = _MutableClock(100_000)
        provider = _CompletePinyinCanaryAdapter()
        staged = StagedContentCandidateGenerator(
            repository=DynamicLearningCourseRepository(self.database),
            adapter=provider,
            clock_ms=clock,
        )
        catalog = LearningCatalogReleaseService(
            self.database_url,
            dynamic_generation_service=None,
            lesson_package_service=None,
            staged_content_candidate_generator=staged,
            primary_one_host_validator=LearningGeneratedCourseValidator(),
            question_phase_provider_profiles=self._profiles(),
            clock_ms=clock,
        )
        repository = _CrashWindowRepository(
            self.database,
            content_proof_auditor=catalog.audit_locked_content_proofs,
            content_provider_dependency_auditor=(
                catalog.audit_content_provider_dependency_retry
            ),
        )
        runner = LearningCurriculumPreparationRunner(
            repository=repository,
            adapter=CheckpointSharedBuildAdapter(
                catalog,
                repository=repository,
                clock=clock,
                plan_lease_ms=90_000,
                heartbeat_interval_ms=15_000,
            ),
            clock=clock,
        )
        reserved = self._reserve_one(repository)
        self._run_planning(runner, clock)
        repository.arm("connection_reset_after_catalog_cas")

        with patch.dict(
            os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False
        ):
            clock.value = 102_000
            recovered = runner.run_once(_runner_app(), now_ms=clock.value)

        with repository.transaction() as conn:
            live = repository.get_plan(conn, str(reserved["id"]))
            dispatches = list(
                conn.execute(
                    """
                    SELECT * FROM learning_course_provider_dispatches
                    ORDER BY phase_ordinal, id
                    """
                ).fetchall()
            )
            item = conn.execute(
                """
                SELECT * FROM learning_catalog_build_items
                WHERE id = ? LIMIT 1
                """,
                (dispatches[0]["build_item_id"],),
            ).fetchone()

        self.assertEqual(recovered["resultCode"], "progressed", recovered)
        self.assertTrue(repository.crashed)
        self.assertEqual(len(dispatches), 1)
        self.assertEqual(dispatches[0]["phase"], "outline")
        self.assertEqual(item["content_phase"], "raw_candidate")
        self.assertEqual(live["status"], "running")
        self.assertEqual(live["stage"], "generating_content")
        self.assertIsNone(live["lease_token"])
        self.assertIsNone(live["hard_deadline_at"])
        self.assertIsNone(live["work_unit_kind"])
        self.assertEqual(provider.execute_calls, 1)

    def test_terminal_fanout_survives_proof_and_item_snapshot_drift(self):
        clock = _MutableClock(100_000)
        provider = _CompletePrimaryOneAdapter()
        catalog, repository, runner = self._runtime(
            clock=clock,
            provider=provider,
            host=_CountingHostValidator(),
        )
        target = build_preparation_target("primary_1")
        fingerprint = preparation_target_fingerprint(target)
        with repository.transaction() as conn:
            plans = [
                repository.reserve_plan(
                    conn,
                    family_id=f"shared_family_{ordinal}",
                    child_id=f"shared_child_{ordinal}",
                    grade_code="primary_1",
                    school_year_start_year=2026,
                    grade_selection_revision=revision,
                    target=target,
                    target_fingerprint=fingerprint,
                    request_id=f"terminal-corrupt-proof-{ordinal}",
                    shared_build_request_id=f"grade-build:{fingerprint}",
                    now=100_000 + ordinal,
                )[0]
                for ordinal, revision in ((1, 2), (2, 9))
            ]
        self._run_planning(runner, clock)
        with repository.transaction() as conn:
            build_id = str(
                repository.get_plan(conn, str(plans[0]["id"]))[
                    "catalog_build_id"
                ]
            )
        with patch.dict(
            os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False
        ):
            results = [
                catalog.advance_content(build_id, heartbeat=lambda: True)
                for _ in range(7)
            ]
        self.assertTrue(
            all(result.kind == "progressed" for result in results), results
        )
        clock.value += 2_000
        with repository.transaction() as conn:
            self.assertEqual(
                repository.reconcile_shared_build(
                    conn,
                    build_id=build_id,
                    target_fingerprint=fingerprint,
                    now=clock.value,
                ),
                2,
            )
            late_owner = repository.claim_next(
                conn,
                now=clock.value + 1_000,
                lease_ms=90_000,
                supported_stages=CheckpointSharedBuildAdapter.supported_stages,
                stage_deadline_ms=runner.STAGE_DEADLINE_MS,
            )
        self.assertIsNotNone(late_owner)
        with repository.transaction() as conn:
            conn.execute(
                """
                UPDATE learning_course_provider_dispatches
                SET output_sha256 = ?
                WHERE build_item_id = ? AND logical_attempt = 1
                  AND phase_ordinal = 1
                """,
                ("0" * 64, results[-1].item_id),
            )
            catalog.repository.fence_content_failure(
                conn,
                build_id=build_id,
                item_id=None,
                error_code="preparation_content_contract_drift",
                now=clock.value + 1_001,
            )
            conn.execute(
                """
                UPDATE learning_catalog_build_items
                SET boundary_version = 'drifted-after-terminal-fence'
                WHERE id = ?
                """,
                (results[-1].item_id,),
            )
        with repository.transaction() as conn:
            with self.assertRaises(ValueError):
                catalog.audit_locked_content_proofs(conn, build_id=build_id)
            failed_count = repository.fail_shared_build_plans(
                conn,
                build_id=build_id,
                target_fingerprint=fingerprint,
                now=clock.value + 1_002,
            )
            failed_plans = [
                repository.get_plan(conn, str(plan["id"])) for plan in plans
            ]
            late_release = repository.release_content_continuation(
                conn,
                plan_id=str(late_owner["id"]),
                plan_lease_token=str(late_owner["lease_token"]),
                target_fingerprint=fingerprint,
                catalog_build_id=build_id,
                next_run_at=clock.value + 2_000,
                now=clock.value + 1_002,
            )

        self.assertEqual(failed_count, 2)
        self.assertFalse(late_release)
        self.assertTrue(
            all(
                plan["status"] == "failed"
                and plan["stage"] == "completed"
                and plan["error_code"] == "preparation_content_contract_drift"
                and plan["lease_token"] is None
                and plan["work_unit_kind"] is None
                for plan in failed_plans
            ),
            failed_plans,
        )

    def test_reconciliation_counts_zero_one_three_partial_twenty_nine_and_handoff(self):
        clock = _MutableClock(100_000)
        provider = _CompletePrimaryOneAdapter()
        host = _CountingHostValidator()
        catalog, repository, runner = self._runtime(
            clock=clock,
            provider=provider,
            host=host,
        )
        target = build_preparation_target("primary_1")
        fingerprint = preparation_target_fingerprint(target)
        with repository.transaction() as conn:
            plans = [
                repository.reserve_plan(
                    conn,
                    family_id=f"shared_family_{ordinal}",
                    child_id=f"shared_child_{ordinal}",
                    grade_code="primary_1",
                    school_year_start_year=2026,
                    grade_selection_revision=revision,
                    target=target,
                    target_fingerprint=fingerprint,
                    request_id=f"count-handoff-plan-{ordinal}",
                    shared_build_request_id=f"grade-build:{fingerprint}",
                    now=100_000 + ordinal,
                )[0]
                for ordinal, revision in ((1, 2), (2, 9))
            ]
        self._run_planning(runner, clock)
        with repository.transaction() as conn:
            planned = [
                repository.get_plan(conn, str(plan["id"])) for plan in plans
            ]
        build_id = str(planned[0]["catalog_build_id"])
        self.assertEqual({str(plan["catalog_build_id"]) for plan in planned}, {build_id})

        def assert_counts(
            candidate_count,
            canary_count,
            *,
            handoff=False,
            exact_owner=False,
        ):
            clock.value += 1_001 if exact_owner else 1
            owner = None
            if exact_owner:
                with repository.transaction() as conn:
                    owner = repository.claim_next(
                        conn,
                        now=clock.value,
                        lease_ms=90_000,
                        supported_stages=("generating_content",),
                        stage_deadline_ms=runner.STAGE_DEADLINE_MS,
                    )
                self.assertIsNotNone(owner)
            with repository.transaction() as conn:
                updated = repository.reconcile_shared_build(
                    conn,
                    build_id=build_id,
                    target_fingerprint=fingerprint,
                    now=clock.value,
                    **(
                        {
                            "owner_plan_id": str(owner["id"]),
                            "owner_lease_token": str(owner["lease_token"]),
                        }
                        if owner is not None
                        else {}
                    ),
                )
                current = [
                    repository.get_plan(conn, str(plan["id"])) for plan in plans
                ]
            self.assertEqual(updated, 2)
            for plan in current:
                self.assertEqual(plan["content_candidate_count"], candidate_count)
                self.assertEqual(plan["content_failed_count"], 0)
                self.assertEqual(plan["content_canary_candidate_count"], canary_count)
                self.assertEqual(plan["content_canary_failed_count"], 0)
                self.assertEqual(plan["ready_course_count"], 0)
                self.assertEqual(plan["failed_course_count"], 0)
                self.assertEqual(plan["progress_percent"], 5 + candidate_count)
                self.assertEqual(
                    json.loads(str(plan["stage_progress_json"])),
                    {
                        "candidateCount": candidate_count,
                        "canaryCandidateCount": canary_count,
                        "canaryFailedCount": 0,
                        "canaryTargetCount": 3,
                        "failedCount": 0,
                        "targetCount": 30,
                    },
                )
                if handoff:
                    self.assertEqual(plan["status"], "running")
                    self.assertEqual(plan["stage"], "building_classrooms")
                    self.assertEqual(plan["progress_percent"], 35)
                    self.assertIsNotNone(plan["content_canary_passed_at"])
                    self.assertIsNotNone(plan["content_generation_completed_at"])
                    for field in (
                        "lease_token",
                        "lease_expires_at",
                        "heartbeat_at",
                        "next_run_at",
                        "hard_deadline_at",
                        "resume_stage",
                        "work_unit_kind",
                        "bound_catalog_item_id",
                        "bound_content_attempt_ordinal",
                        "bound_content_phase",
                        "retry_reason_code",
                        "retry_message_safe",
                    ):
                        self.assertIsNone(plan[field], (field, dict(plan)))
                else:
                    self.assertEqual(plan["status"], "running")
                    self.assertEqual(plan["stage"], "generating_content")
            if owner is not None:
                owner_plan = next(
                    plan for plan in current if str(plan["id"]) == str(owner["id"])
                )
                self.assertEqual(owner_plan["lease_token"], owner["lease_token"])
                with repository.transaction() as conn:
                    self.assertTrue(
                        repository.release_content_continuation(
                            conn,
                            plan_id=str(owner["id"]),
                            plan_lease_token=str(owner["lease_token"]),
                            target_fingerprint=fingerprint,
                            catalog_build_id=build_id,
                            next_run_at=clock.value + 1,
                            now=clock.value,
                        )
                    )
            return current

        assert_counts(0, 0)
        completed = 0
        with patch.dict(os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False):
            for target_count, canary_count in ((1, 1), (3, 3), (4, 3), (29, 3), (30, 3)):
                while completed < target_count:
                    results = [
                        catalog.advance_content(build_id, heartbeat=lambda: True)
                        for _ in range(7)
                    ]
                    self.assertTrue(
                        all(result.kind == "progressed" for result in results),
                        results,
                    )
                    completed += 1
                final_plans = assert_counts(
                    target_count,
                    canary_count,
                    handoff=target_count == 30,
                    exact_owner=target_count in {1, 29},
                )
                if target_count == 29:
                    clock.value += 2_000
                    with repository.transaction() as conn:
                        late_owner = repository.claim_next(
                            conn,
                            now=clock.value,
                            lease_ms=90_000,
                            supported_stages=CheckpointSharedBuildAdapter.supported_stages,
                            stage_deadline_ms=runner.STAGE_DEADLINE_MS,
                        )
                    self.assertIsNotNone(late_owner)

                    class RollbackTerminalProbe(RuntimeError):
                        pass

                    with self.assertRaises(RollbackTerminalProbe):
                        with repository.transaction() as conn:
                            catalog.repository.fence_content_failure(
                                conn,
                                build_id=build_id,
                                item_id=None,
                                error_code="preparation_content_provider_unavailable",
                                now=clock.value + 1,
                            )
                            failed_count = repository.fail_shared_build_plans(
                                conn,
                                build_id=build_id,
                                target_fingerprint=fingerprint,
                                now=clock.value + 1,
                            )
                            failed_plans = [
                                repository.get_plan(conn, str(plan["id"]))
                                for plan in plans
                            ]
                            self.assertEqual(failed_count, 2)
                            self.assertTrue(
                                all(
                                    plan["status"] == "failed"
                                    and plan["stage"] == "completed"
                                    and plan["content_candidate_count"] == 29
                                    and plan["error_code"]
                                    == "preparation_content_provider_unavailable"
                                    for plan in failed_plans
                                ),
                                failed_plans,
                            )
                            self.assertFalse(
                                repository.release_content_continuation(
                                    conn,
                                    plan_id=str(late_owner["id"]),
                                    plan_lease_token=str(late_owner["lease_token"]),
                                    target_fingerprint=fingerprint,
                                    catalog_build_id=build_id,
                                    next_run_at=clock.value + 2_000,
                                    now=clock.value + 1,
                                )
                            )
                            raise RollbackTerminalProbe()
                    with repository.transaction() as conn:
                        self.assertTrue(
                            repository.release_content_continuation(
                                conn,
                                plan_id=str(late_owner["id"]),
                                plan_lease_token=str(late_owner["lease_token"]),
                                target_fingerprint=fingerprint,
                                catalog_build_id=build_id,
                                next_run_at=clock.value + 2_000,
                                now=clock.value + 1,
                            )
                        )
            handoff_result = catalog.advance_content(
                build_id, heartbeat=lambda: True
            )

        self.assertEqual(handoff_result.kind, "handoff", handoff_result)
        self.assertEqual(provider.execute_calls, 180)
        self.assertTrue(
            all(plan["content_candidate_count"] == 30 for plan in final_plans)
        )
        self.assertEqual(
            runner.run_once(_runner_app(), now_ms=clock.value + 1),
            {"claimed": 0},
        )
        with repository.transaction() as conn:
            dispatch_count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches"
            ).fetchone()["count"]
            passed_item_count = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM learning_catalog_build_items
                WHERE status = 'course_ready'
                  AND content_phase = 'course_ready'
                  AND content_gate_status = 'passed'
                  AND content_gate_attempt_count = 1
                  AND content_receipt_hash IS NOT NULL
                  AND course_id IS NOT NULL AND course_version IS NOT NULL
                """
            ).fetchone()["count"]
            forbidden_package_count = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM learning_catalog_build_items
                WHERE package_attempt_count <> 0
                   OR active_package_request_id IS NOT NULL
                   OR package_id IS NOT NULL OR package_version IS NOT NULL
                """
            ).fetchone()["count"]
            publication_count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_catalog_release_items"
            ).fetchone()["count"]
            classroom_job_count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_classroom_generation_jobs"
            ).fetchone()["count"]
            runtime_classroom_count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_openmaic_runtime_classrooms"
            ).fetchone()["count"]
        self.assertEqual(dispatch_count, 180)
        self.assertEqual(passed_item_count, 30)
        self.assertGreaterEqual(host.host_calls, 30)
        self.assertEqual(forbidden_package_count, 0)
        self.assertEqual(publication_count, 0)
        self.assertEqual(classroom_job_count, 0)
        self.assertEqual(runtime_classroom_count, 0)

    def test_runner_persists_first_and_twenty_ninth_host_pass_before_owner_release(self):
        clock = _MutableClock(100_000)
        provider = _CompletePrimaryOneAdapter()
        host = _CountingHostValidator()
        catalog, repository, runner = self._runtime(
            clock=clock,
            provider=provider,
            host=host,
        )
        reserved = self._reserve_one(repository)
        self._run_planning(runner, clock)
        observed_owner_progress = []
        original_reconcile = repository.reconcile_shared_build

        def observe_reconcile(conn, **kwargs):
            updated = original_reconcile(conn, **kwargs)
            current = repository.get_plan(conn, str(reserved["id"]))
            candidate_count = int(current["content_candidate_count"])
            if candidate_count in {1, 29}:
                observed_owner_progress.append(
                    {
                        "candidateCount": candidate_count,
                        "leaseToken": current["lease_token"],
                        "ownerLeaseToken": kwargs["owner_lease_token"],
                        "workUnitKind": current["work_unit_kind"],
                        "boundItemId": current["bound_catalog_item_id"],
                        "boundPhase": current["bound_content_phase"],
                    }
                )
            return updated

        def run_one_item_through_runner():
            results = []
            for _ in range(7):
                clock.value += 2_000
                results.append(
                    runner.run_once(_runner_app(), now_ms=clock.value)
                )
            self.assertTrue(
                all(result.get("resultCode") == "progressed" for result in results),
                results,
            )

        with patch.dict(
            os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False
        ), patch.object(
            repository,
            "reconcile_shared_build",
            side_effect=observe_reconcile,
        ):
            run_one_item_through_runner()
            with repository.transaction() as conn:
                first = repository.get_plan(conn, str(reserved["id"]))
            self._assert_runner_content_progress(first, candidate_count=1)

            for _ in range(27):
                direct_results = [
                    catalog.advance_content(
                        build_id=str(first["catalog_build_id"]),
                        heartbeat=lambda: True,
                    )
                    for _ in range(7)
                ]
                self.assertTrue(
                    all(result.kind == "progressed" for result in direct_results),
                    direct_results,
                )
            with repository.transaction() as conn:
                before_twenty_ninth = repository.get_plan(
                    conn, str(reserved["id"])
                )
            self.assertEqual(before_twenty_ninth["content_candidate_count"], 1)

            run_one_item_through_runner()

        with repository.transaction() as conn:
            twenty_ninth = repository.get_plan(conn, str(reserved["id"]))
        self._assert_runner_content_progress(twenty_ninth, candidate_count=29)
        for candidate_count in (1, 29):
            observation = next(
                value
                for value in observed_owner_progress
                if value["candidateCount"] == candidate_count
            )
            self.assertEqual(
                observation["leaseToken"], observation["ownerLeaseToken"]
            )
            self.assertIn(
                observation["workUnitKind"], {"provider_phase", "host_gate"}
            )
            self.assertIsNotNone(observation["boundItemId"])
            self.assertIsNotNone(observation["boundPhase"])
        for field in (
            "lease_token",
            "lease_expires_at",
            "heartbeat_at",
            "hard_deadline_at",
            "work_unit_kind",
            "bound_catalog_item_id",
            "bound_content_attempt_ordinal",
            "bound_content_phase",
        ):
            self.assertIsNone(twenty_ninth[field], (field, dict(twenty_ninth)))

    def _assert_runner_content_progress(self, plan, *, candidate_count):
        self.assertEqual(plan["status"], "running")
        self.assertEqual(plan["stage"], "generating_content")
        self.assertEqual(plan["content_target_count"], 30)
        self.assertEqual(plan["content_candidate_count"], candidate_count)
        self.assertEqual(plan["content_failed_count"], 0)
        self.assertEqual(plan["content_canary_target_count"], 3)
        self.assertEqual(
            plan["content_canary_candidate_count"], min(candidate_count, 3)
        )
        self.assertEqual(plan["content_canary_failed_count"], 0)
        self.assertEqual(plan["progress_percent"], 5 + candidate_count)
        subject_progress = json.loads(str(plan["subject_progress_json"]))
        expected_by_subject = (
            {"chinese": 1, "math": 0, "english": 0}
            if candidate_count == 1
            else {"chinese": 11, "math": 9, "english": 9}
        )
        self.assertEqual(
            {
                subject: progress["contentCandidateCount"]
                for subject, progress in subject_progress.items()
            },
            expected_by_subject,
        )
        self.assertEqual(
            sum(
                progress["contentCandidateCount"]
                for progress in subject_progress.values()
            ),
            candidate_count,
        )
        self.assertTrue(
            all(
                progress["readyCourseCount"] == 0
                and progress["failedCourseCount"] == 0
                and progress["contentFailedCount"] == 0
                for progress in subject_progress.values()
            ),
            subject_progress,
        )

    def test_real_host_only_parent_get_and_locked_post_use_lazy_pure_auditor(self):
        from routes.api.v1.learning import learning_bp
        from services.learning_curriculum_preparation_service import (
            LearningCurriculumPreparationService,
        )
        from services.service_factory import (
            learning_curriculum_preparation_parent_retry_repository,
        )

        clock = _MutableClock(100_000)
        provider = _BindingObservedPinyinAdapter(self.database)
        provider.provider_timeout_ms = 60_000
        provider.max_tokens = 8_000
        provider.process_timeout_seconds = 75.0
        host = _BindingObservedHostValidator(self.database)
        factory_profiles = {
            role: {
                "name": "kimi",
                "model": "moonshot-v1-8k",
                "baseUrl": "https://api.moonshot.cn/v1",
                "apiKeyEnv": "APP_AI_API_KEY",
                "timeoutMs": 60_000,
                "maxTokens": 8_000,
                "temperature": 0.2,
            }
            for role in ("generator", "verifier")
        }
        _catalog, repository, runner = self._runtime(
            clock=clock,
            provider=provider,
            host=host,
            profiles=factory_profiles,
        )
        plan = self._reserve_one(repository)
        clock.value = 101_000
        self.assertEqual(
            runner.run_once(_runner_app(), now_ms=clock.value)["resultCode"],
            "progressed",
        )
        with patch.dict(os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False):
            for _ in range(6):
                clock.value += 2_000
                phase_result = runner.run_once(_runner_app(), now_ms=clock.value)
                if phase_result["resultCode"] != "progressed":
                    with repository.transaction() as conn:
                        diagnostics = {
                            "plan": dict(repository.get_plan(conn, str(plan["id"]))),
                            "items": list(
                                conn.execute(
                                    """
                                    SELECT status, content_phase, error_code,
                                      error_message_safe
                                    FROM learning_catalog_build_items
                                    ORDER BY subject_ordinal, boundary_ordinal,
                                      variant_ordinal
                                    LIMIT 2
                                    """
                                ).fetchall()
                            ),
                        }
                    self.fail({"result": phase_result, **diagnostics})
                self.assertEqual(
                    phase_result["resultCode"],
                    "progressed",
                    phase_result,
                )
        self.assertEqual(provider.execute_calls, 6)
        with repository.transaction() as conn:
            source = repository.get_plan(conn, str(plan["id"]))
            authority = repository.load_parent_retry_authority(
                conn,
                plan=source,
                lock=False,
            )
            conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET status = 'failed', stage = 'completed', next_run_at = NULL,
                  lease_token = NULL, lease_expires_at = NULL,
                  heartbeat_at = NULL, hard_deadline_at = NULL,
                  resume_stage = NULL, work_unit_kind = NULL,
                  bound_catalog_item_id = NULL,
                  bound_content_attempt_ordinal = NULL,
                  bound_content_phase = NULL, retry_reason_code = NULL,
                  retry_message_safe = NULL, superseded_at = NULL,
                  error_code = 'preparation_dependency_unavailable',
                  error_message_safe = '课程服务暂时不可用，请稍后重试',
                  completed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (clock.value, clock.value, plan["id"]),
            )
            dispatch_before = int(
                conn.execute(
                    "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches"
                ).fetchone()["count"]
            )
        self.assertEqual(authority.authority_class, "host_only_dependency")

        class _Auth:
            @staticmethod
            def authenticate(access_token):
                if access_token != "task9-host-only-token":
                    raise AssertionError("unexpected access token")
                return {"family": {"id": "shared_family_1"}}

        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            DATABASE_URL=self.database_url,
            AI_PROVIDER="kimi",
            AI_MODEL="moonshot-v1-8k",
            AI_BASE_URL="https://api.moonshot.cn/v1",
        )
        app.register_blueprint(learning_bp, url_prefix="/api/learning")
        app.extensions["mira_learning_curriculum_preparation_service"] = (
            LearningCurriculumPreparationService(
                self.database_url,
                auth_service=_Auth(),
                repository=LearningCurriculumPreparationRepository(self.database),
                retry_repository_factory=(
                    learning_curriculum_preparation_parent_retry_repository
                ),
            )
        )
        client = app.test_client()
        headers = {
            "Authorization": "Bearer task9-host-only-token",
            PREPARATION_SCHEMA_HEADER: "mira.learning.preparation.v2",
        }
        zero_guard_evidence = {}
        zero_guard = _RequestPathSideEffectGuard()
        locked_sql: list[str] = []
        original_execute = DatabaseConnection.execute

        def record_locked_sql(connection, sql, params=()):
            normalized = " ".join(sql.split())
            if "FOR UPDATE" in normalized.upper():
                locked_sql.append(normalized)
            return original_execute(connection, sql, params)

        with patch(
            "services.service_factory.learning_curriculum_preparation_checkpoint_adapter",
            side_effect=AssertionError("parent retry resolved execution adapter"),
        ) as checkpoint_adapter, patch(
            "services.service_factory.OpenMaicQuestionPhaseAdapter",
            side_effect=AssertionError("parent retry constructed Provider adapter"),
        ) as provider_adapter, patch(
            "subprocess.Popen",
            side_effect=AssertionError("parent retry started a process"),
        ) as process, patch.object(
            DatabaseConnection,
            "execute",
            record_locked_sql,
        ):
            with zero_guard.installed():
                snapshot = zero_guard.snapshot()
                current = client.get(
                    "/api/learning/preparations/current",
                    query_string={"childId": "shared_child_1"},
                    headers=headers,
                )
                zero_guard_evidence["host_only_current"] = zero_guard.delta(
                    snapshot
                )
            with repository.transaction() as conn:
                source_dispatch = conn.execute(
                    """
                    SELECT * FROM learning_course_provider_dispatches
                    ORDER BY dispatched_at, id LIMIT 1
                    """
                ).fetchone()
                future_item = conn.execute(
                    """
                    SELECT * FROM learning_catalog_build_items
                    WHERE build_job_id = ? AND status = 'pending'
                    ORDER BY subject_ordinal, boundary_ordinal,
                      variant_ordinal, id LIMIT 1
                    """,
                    (source["catalog_build_id"],),
                ).fetchone()
                self.assertIsNotNone(source_dispatch)
                self.assertIsNotNone(future_item)
                conn.execute(
                    """
                    INSERT INTO learning_course_provider_dispatches(
                      id, build_item_id, logical_attempt, phase, phase_ordinal,
                      generation_request_id, item_lease_token, provider, model,
                      profile, input_sha256, status, checkpoint_json,
                      output_sha256, attempt_started_at,
                      attempt_hard_deadline_at, provider_request_id_hash,
                      input_tokens, output_tokens, billing_evidence,
                      safe_error_code, dispatched_at, completed_at
                    )
                    SELECT 'task9-stale-display-residue', ?, 1, phase,
                      phase_ordinal, ?, item_lease_token, provider, model,
                      profile, input_sha256, 'succeeded', checkpoint_json,
                      output_sha256, attempt_started_at,
                      attempt_hard_deadline_at, provider_request_id_hash,
                      input_tokens, output_tokens, billing_evidence,
                      safe_error_code, dispatched_at, completed_at
                    FROM learning_course_provider_dispatches
                    WHERE id = ?
                    """,
                    (
                        future_item["id"],
                        future_item["generation_request_id"],
                        source_dispatch["id"],
                    ),
                )
            locked_sql.clear()
            with zero_guard.installed():
                snapshot = zero_guard.snapshot()
                rejected = client.post(
                    f"/api/learning/preparations/{plan['id']}/retry",
                    json={"requestId": "task9-host-only-retry"},
                    headers=headers,
                )
                zero_guard_evidence["host_only_retry_rejected"] = (
                    zero_guard.delta(snapshot)
                )
            with repository.transaction() as conn:
                successor_count_after_rejection = int(
                    conn.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM learning_curriculum_preparation_plans
                        WHERE retry_of_plan_id = ?
                        """,
                        (plan["id"],),
                    ).fetchone()["count"]
                )
                dispatch_after_rejection = int(
                    conn.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM learning_course_provider_dispatches
                        """
                    ).fetchone()["count"]
                )
                conn.execute(
                    """
                    DELETE FROM learning_course_provider_dispatches
                    WHERE id = ?
                    """,
                    ("task9-stale-display-residue",),
                )
            with zero_guard.installed():
                snapshot = zero_guard.snapshot()
                retried = client.post(
                    f"/api/learning/preparations/{plan['id']}/retry",
                    json={"requestId": "task9-host-only-retry"},
                    headers=headers,
                )
                zero_guard_evidence["host_only_retry_accepted"] = (
                    zero_guard.delta(snapshot)
                )

        self.assertEqual(current.status_code, 200, current.json)
        lazy_repository = app.extensions.get(
            "mira_learning_curriculum_preparation_parent_retry_repository"
        )
        self.assertIsInstance(
            lazy_repository,
            LearningCurriculumPreparationRepository,
        )
        with lazy_repository.transaction() as conn:
            lazy_source = lazy_repository.get_plan(conn, str(plan["id"]))
            persisted_profiles = tuple(
                conn.execute(
                    """
                    SELECT DISTINCT provider, model, profile
                    FROM learning_course_provider_dispatches
                    ORDER BY provider, model, profile
                    """
                ).fetchall()
            )
            lazy_authority = lazy_repository.load_parent_retry_authority(
                conn,
                plan=lazy_source,
                lock=False,
            )
        audit_service = lazy_repository.content_parent_retry_auditor.__self__
        expected_profiles = {
            role: audit_service._content_profile_evidence(role).profile_hash
            for role in ("generator", "verifier")
        }
        self.assertEqual(
            lazy_authority.authority_class,
            "host_only_dependency",
            {
                "authority": lazy_authority,
                "persistedProfiles": persisted_profiles,
                "expectedProfiles": expected_profiles,
            },
        )
        self.assertTrue(current.json["preparation"]["canRetry"])
        self.assertEqual(rejected.status_code, 409, rejected.json)
        self.assertEqual(successor_count_after_rejection, 0)
        self.assertEqual(dispatch_after_rejection, dispatch_before + 1)
        self.assertEqual(retried.status_code, 202, retried.json)
        for response in (current, rejected, retried):
            self.assertIn(
                PREPARATION_SCHEMA_HEADER,
                response.headers.get("Vary", ""),
            )
        self.assertEqual(
            current.json["preparation"]["schemaVersion"],
            "mira.learning.preparation.v2",
        )
        self.assertEqual(
            retried.json["preparation"]["schemaVersion"],
            "mira.learning.preparation.v2",
        )
        self.assertEqual(checkpoint_adapter.call_count, 0)
        self.assertEqual(provider_adapter.call_count, 0)
        self.assertEqual(process.call_count, 0)
        self.assertTrue(
            any(
                "learning_catalog_build_items" in statement
                and "FOR UPDATE" in statement.upper()
                for statement in locked_sql
            ),
            locked_sql,
        )
        with repository.transaction() as conn:
            dispatch_after = int(
                conn.execute(
                    "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches"
                ).fetchone()["count"]
            )
        self.assertEqual(dispatch_after, dispatch_before)
        self.assertEqual(provider.execute_calls, 6)
        zero_counts = {category: 0 for category in SIDE_EFFECT_CATEGORIES}
        self.assertEqual(
            zero_guard_evidence,
            {
                "host_only_current": zero_counts,
                "host_only_retry_rejected": zero_counts,
                "host_only_retry_accepted": zero_counts,
            },
        )

    def test_two_revision_distinct_children_share_one_bound_paid_work_graph(self):
        clock = _MutableClock(100_000)
        provider = _BindingObservedPinyinAdapter(self.database)
        host = _BindingObservedHostValidator(self.database)
        staged = StagedContentCandidateGenerator(
            repository=DynamicLearningCourseRepository(self.database),
            adapter=provider,
            clock_ms=clock,
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
        catalog = LearningCatalogReleaseService(
            self.database_url,
            dynamic_generation_service=None,
            lesson_package_service=None,
            staged_content_candidate_generator=staged,
            primary_one_host_validator=host,
            question_phase_provider_profiles=profiles,
            clock_ms=clock,
        )
        audit_calls = []

        def audited(conn, *, build_id):
            audit_calls.append(build_id)
            return catalog.audit_locked_content_proofs(
                conn, build_id=build_id
            )

        repository = LearningCurriculumPreparationRepository(
            self.database,
            content_proof_auditor=audited,
            content_dispatch_graph_auditor=(
                catalog.audit_content_host_retry_graph
            ),
            content_parent_retry_auditor=(
                catalog.audit_content_parent_retry_authority
            ),
            content_provider_dependency_auditor=(
                catalog.audit_content_provider_dependency_retry
            ),
        )
        target = build_preparation_target("primary_1")
        fingerprint = preparation_target_fingerprint(target)
        shared_request = f"grade-build:{fingerprint}"
        with repository.transaction() as conn:
            plans = [
                repository.reserve_plan(
                    conn,
                    family_id=f"shared_family_{ordinal}",
                    child_id=f"shared_child_{ordinal}",
                    grade_code="primary_1",
                    school_year_start_year=2026,
                    grade_selection_revision=revision,
                    target=target,
                    target_fingerprint=fingerprint,
                    request_id=f"shared-plan-{ordinal}",
                    shared_build_request_id=shared_request,
                    now=100_000 + ordinal,
                )[0]
                for ordinal, revision in ((1, 2), (2, 9))
            ]
        adapter = CheckpointSharedBuildAdapter(
            catalog,
            repository=repository,
            clock=clock,
            plan_lease_ms=90_000,
            heartbeat_interval_ms=15_000,
        )
        runner = LearningCurriculumPreparationRunner(
            repository=repository,
            adapter=adapter,
            clock=clock,
        )
        app = _runner_app()

        clock.value = 101_000
        planning = runner.run_once(app, now_ms=clock.value)
        self.assertEqual(planning.get("resultCode"), "progressed", planning)
        self.assertEqual(provider.execute_calls, 0)
        with repository.transaction() as conn:
            planned = [repository.get_plan(conn, str(plan["id"])) for plan in plans]
        self.assertEqual(len({str(plan["catalog_build_id"]) for plan in planned}), 1)
        self.assertEqual(
            {int(plan["grade_selection_revision"]) for plan in planned},
            {2, 9},
        )
        self.assertTrue(all(plan["stage"] == "generating_content" for plan in planned))
        self.assertTrue(all(plan["lease_token"] is None for plan in planned))
        self.assertTrue(all(plan["hard_deadline_at"] is None for plan in planned))
        with repository.transaction() as conn:
            pre_provider = repository.load_parent_retry_authority(
                conn,
                plan=repository.get_plan(conn, str(plans[0]["id"])),
                lock=False,
            )
        self.assertEqual(pre_provider.authority_class, "pre_provider_dependency")
        self.assertEqual(pre_provider.provider_dispatch_count, 0)
        self.assertFalse(pre_provider.provider_graph_complete)
        self.assertIsNone(pre_provider.next_work_kind)

        provider_deltas = []
        content_results = []
        with patch.dict(os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False):
            for _ in range(6):
                before = provider.execute_calls
                clock.value += 2_000
                content_results.append(
                    runner.run_once(app, now_ms=clock.value)
                )
                provider_deltas.append(provider.execute_calls - before)
            with repository.transaction() as conn:
                raw_items = list(
                    conn.execute(
                        """
                        SELECT * FROM learning_catalog_build_items
                        WHERE build_job_id = ?
                        ORDER BY subject_ordinal, boundary_ordinal,
                          variant_ordinal, id
                        """,
                        (planned[0]["catalog_build_id"],),
                    ).fetchall()
                )
                raw_dispatches = list(
                    conn.execute(
                        """
                        SELECT * FROM learning_course_provider_dispatches
                        WHERE build_item_id IN (
                          SELECT id FROM learning_catalog_build_items
                          WHERE build_job_id = ?
                        )
                        ORDER BY build_item_id, logical_attempt,
                          phase_ordinal, id
                        """,
                        (planned[0]["catalog_build_id"],),
                    ).fetchall()
                )
                host_item = next(
                    item
                    for item in raw_items
                    if item["content_phase"] == "host_gate_pending"
                )
                histories = repository._load_parent_retry_attempt_histories(
                    conn,
                    items=raw_items,
                    dispatches=raw_dispatches,
                    lock=False,
                )
                current_history = histories[str(host_item["id"])][1]
                self.assertEqual(
                    {
                        key: len(current_history[key])
                        for key in (
                            "dispatches",
                            "jobs",
                            "candidates",
                            "courses",
                        )
                    },
                    {
                        "dispatches": 6,
                        "jobs": 1,
                        "candidates": 1,
                        "courses": 0,
                    },
                    current_history,
                )
                direct_graph = catalog.audit_content_host_retry_graph(
                    evidence={
                        "item": dict(host_item),
                        "attemptHistories": histories[str(host_item["id"])],
                    },
                    prior_evidence=(),
                )
                select_only_conn = _SqlRecordingProxy(conn)
                host_only = repository.load_parent_retry_authority(
                    select_only_conn,
                    plan=repository.get_plan(conn, str(plans[0]["id"])),
                    lock=False,
                )
                future_item = next(
                    item
                    for item in raw_items
                    if str(item.get("status") or "") == "pending"
                )
                conn.execute(
                    """
                    INSERT INTO learning_course_provider_dispatches(
                      id, build_item_id, logical_attempt, phase, phase_ordinal,
                      generation_request_id, item_lease_token, provider, model,
                      profile, input_sha256, status, checkpoint_json,
                      output_sha256, attempt_started_at,
                      attempt_hard_deadline_at, provider_request_id_hash,
                      input_tokens, output_tokens, billing_evidence,
                      safe_error_code, dispatched_at, completed_at
                    )
                    SELECT ?, ?, 1, phase, phase_ordinal, ?, item_lease_token,
                      provider, model, profile, input_sha256, 'succeeded',
                      checkpoint_json, output_sha256, attempt_started_at,
                      attempt_hard_deadline_at, provider_request_id_hash,
                      input_tokens, output_tokens, billing_evidence,
                      safe_error_code, dispatched_at, completed_at
                    FROM learning_course_provider_dispatches
                    WHERE id = ?
                    """,
                    (
                        "task8-future-dispatch-residue",
                        future_item["id"],
                        future_item["generation_request_id"],
                        raw_dispatches[0]["id"],
                    ),
                )
                future_residue = repository.load_parent_retry_authority(
                    conn,
                    plan=repository.get_plan(conn, str(plans[0]["id"])),
                    lock=False,
                )
                conn.execute(
                    "DELETE FROM learning_course_provider_dispatches WHERE id = ?",
                    ("task8-future-dispatch-residue",),
                )
                missing_graph_auditor = LearningCurriculumPreparationRepository(
                    self.database,
                    content_proof_auditor=catalog.audit_locked_content_proofs,
                ).load_parent_retry_authority(
                    conn,
                    plan=repository.get_plan(conn, str(plans[0]["id"])),
                    lock=False,
                )
                locked_context = repository.lock_parent_retry_context(
                    conn,
                    family_id="shared_family_1",
                    plan_id=str(plans[0]["id"]),
                )
            self.assertIsInstance(
                direct_graph, ContentDispatchGraphAuditSnapshot
            )
            self.assertTrue(select_only_conn.statements)
            self.assertTrue(
                all(
                    "FOR UPDATE" not in statement.upper()
                    and statement.lstrip().upper().startswith("SELECT")
                    for statement in select_only_conn.statements
                ),
                select_only_conn.statements,
            )
            self.assertEqual(host_only.authority_class, "host_only_dependency")
            self.assertEqual(
                future_residue.authority_class,
                "not_replayable",
            )
            self.assertEqual(
                missing_graph_auditor.authority_class,
                "not_replayable",
            )
            self.assertEqual(host_only.provider_dispatch_count, 6)
            self.assertEqual(host_only.open_or_ambiguous_dispatch_count, 0)
            self.assertEqual(host_only.failed_safe_dispatch_count, 0)
            self.assertTrue(host_only.provider_graph_complete)
            self.assertEqual(host_only.next_work_kind, "host_gate")
            self.assertIsNotNone(locked_context)
            self.assertEqual(locked_context[2], host_only)

            before = provider.execute_calls
            clock.value += 2_000
            content_results.append(runner.run_once(app, now_ms=clock.value))
            provider_deltas.append(provider.execute_calls - before)

        with repository.transaction() as conn:
            zero_provider_diagnostic = {
                "plans": [
                    dict(repository.get_plan(conn, str(plan["id"])))
                    for plan in plans
                ],
                "items": [
                    dict(item)
                    for item in conn.execute(
                        """
                        SELECT id, status, attempt_count, content_phase,
                          content_gate_status, content_lease_token,
                          content_work_unit_deadline_at
                        FROM learning_catalog_build_items
                        WHERE build_job_id = ?
                        ORDER BY subject_ordinal, boundary_ordinal,
                          variant_ordinal, id
                        """,
                        (planned[0]["catalog_build_id"],),
                    ).fetchall()
                ],
            }

        self.assertEqual(
            provider_deltas,
            [1, 1, 1, 1, 1, 1, 0],
            {"results": content_results, **zero_provider_diagnostic},
        )
        self.assertTrue(
            all(result["resultCode"] == "progressed" for result in content_results)
        )
        self.assertEqual(len(provider.binding_observations), 6)
        self.assertTrue(
            all(
                observation["workKind"] == "provider_phase"
                and observation["planDeadline"] == observation["itemDeadline"]
                for observation in provider.binding_observations
            )
        )
        self.assertEqual(len(host.binding_observations), 1)
        self.assertEqual(host.binding_observations[0]["workKind"], "host_gate")
        self.assertEqual(host.binding_observations[0]["phase"], "host_gate_running")
        self.assertEqual(
            host.binding_observations[0]["planDeadline"],
            host.binding_observations[0]["itemDeadline"],
        )

        with repository.transaction() as conn:
            final_plans = [
                repository.get_plan(conn, str(plan["id"])) for plan in plans
            ]
            dispatch_count = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM learning_course_provider_dispatches
                """
            ).fetchone()["count"]
            ready_item_count = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM learning_catalog_build_items
                WHERE status = 'course_ready'
                """
            ).fetchone()["count"]
            forbidden_package_count = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM learning_catalog_build_items
                WHERE package_attempt_count <> 0
                   OR active_package_request_id IS NOT NULL
                   OR package_id IS NOT NULL OR package_version IS NOT NULL
                """
            ).fetchone()["count"]
            publication_count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_catalog_release_items"
            ).fetchone()["count"]

        self.assertEqual(dispatch_count, 6)
        self.assertEqual(ready_item_count, 1)
        self.assertEqual(forbidden_package_count, 0)
        self.assertEqual(publication_count, 0)
        self.assertGreaterEqual(len(audit_calls), 8)
        self.assertEqual(len(set(audit_calls)), 1)
        self.assertEqual(
            {str(plan["catalog_build_id"]) for plan in final_plans},
            set(audit_calls),
        )
        self.assertIn(1, {int(plan["content_candidate_count"]) for plan in final_plans})
        self.assertTrue(all(plan["ready_course_count"] == 0 for plan in final_plans))
        self.assertTrue(all(plan["failed_course_count"] == 0 for plan in final_plans))
        self.assertTrue(all(plan["lease_token"] is None for plan in final_plans))
        self.assertTrue(all(plan["hard_deadline_at"] is None for plan in final_plans))


if __name__ == "__main__":
    unittest.main()
