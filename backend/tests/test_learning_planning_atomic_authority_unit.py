from __future__ import annotations

import copy
from contextlib import contextmanager
import json
import unittest

from repositories.learning_curriculum_preparation_repository import (
    LearningCurriculumPreparationRepository,
)
from services.learning_catalog_release_service import LearningCatalogReleaseService
from services.learning_curriculum_preparation_contract import (
    build_preparation_target,
    preparation_target_fingerprint,
)
from services.learning_curriculum_preparation_runner import (
    CheckpointSharedBuildAdapter,
    PreparationDeterministicError,
)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _subject_progress() -> dict[str, dict[str, int]]:
    return {
        subject: {
            "totalCourseCount": total,
            "readyCourseCount": 0,
            "failedCourseCount": 0,
        }
        for subject, total in (("chinese", 12), ("math", 9), ("english", 9))
    }


def _planning_plan() -> dict[str, object]:
    target = build_preparation_target("primary_1")
    fingerprint = preparation_target_fingerprint(target)
    return {
        "id": "plan-atomic-authority",
        "family_id": "family-1",
        "child_id": "child-1",
        "status": "running",
        "stage": "planning",
        "target_fingerprint": fingerprint,
        "shared_build_request_id": f"grade-build:{fingerprint}",
        "grade_code": "primary_1",
        "grade_selection_revision": 7,
        "curriculum_version": target["curriculumVersion"],
        "preparation_contract_version": target["preparationContractVersion"],
        "target_spec_json": _canonical_json(target),
        "ready_course_count": 0,
        "failed_course_count": 0,
        "subject_progress_json": _subject_progress(),
        "catalog_build_id": None,
        "catalog_release_id": None,
        "lease_token": "planning-lease",
        "lease_expires_at": 5_000,
        "heartbeat_at": 1_000,
        "next_run_at": 1_000,
        "hard_deadline_at": 5_000,
        "resume_stage": None,
        "work_unit_kind": "coordinator",
        "bound_catalog_item_id": None,
        "bound_content_attempt_ordinal": None,
        "bound_content_phase": None,
        "retry_reason_code": None,
        "retry_message_safe": None,
        "completed_at": None,
        "superseded_at": None,
    }


class _CatalogRepository:
    def __init__(self):
        self.conn = object()
        self.in_transaction = False
        self.create_calls = 0
        self.release_reads = 0
        self.item_reads = 0

    @contextmanager
    def transaction(self):
        if self.in_transaction:
            raise AssertionError("catalog transaction nested")
        self.in_transaction = True
        try:
            yield self.conn
        finally:
            self.in_transaction = False

    @staticmethod
    def encode_json(value: object) -> str:
        return _canonical_json(value)

    def create_or_get_content_build(self, conn, **kwargs):
        if not self.in_transaction or conn is not self.conn:
            raise AssertionError("catalog build escaped its transaction")
        self.create_calls += 1
        return (
            {
                "id": "catalog-build-1",
                "request_id": kwargs["request_id"],
                "release_id": "catalog-release-1",
                "status": "queued",
                "curriculum_version": kwargs["curriculum_version"],
                "total_item_count": 30,
                "ready_item_count": 0,
                "failed_item_count": 0,
                "execution_mode": "content_only",
                "stage_ceiling": "content_ready",
            },
            True,
        )

    def get_release(self, conn, **_kwargs):
        if not self.in_transaction or conn is not self.conn:
            raise AssertionError("release read escaped its transaction")
        self.release_reads += 1
        return {
            "id": "catalog-release-1",
            "title": "Mira primary_1 正式课程",
            "status": "draft",
            "quality_status": "building",
            "curriculum_version": build_preparation_target("primary_1")[
                "curriculumVersion"
            ],
            "required_boundary_count": 10,
            "ready_item_count": 0,
            "activated_at": None,
        }

    def list_build_items(self, conn, **_kwargs):
        if not self.in_transaction or conn is not self.conn:
            raise AssertionError("item read escaped its transaction")
        self.item_reads += 1
        return []

    def get_build_release_readiness(self, conn, **_kwargs):
        if not self.in_transaction or conn is not self.conn:
            raise AssertionError("readiness read escaped its transaction")
        return {
            "releaseReadyItemCount": 0,
            "mediaPendingItemCount": 0,
        }


class _ForbiddenDependency:
    def __init__(self):
        self.access_count = 0

    def __getattr__(self, name):
        self.access_count += 1
        raise AssertionError(f"planning accessed forbidden dependency: {name}")


class _PlanningRepository:
    def __init__(self, *, catalog: _CatalogRepository, drift: str | None):
        self.catalog = catalog
        self.plan = _planning_plan()
        self.child = {
            "id": "child-1",
            "family_id": "family-1",
            "grade_code": "primary_1",
            "grade_selection_revision": 7,
        }
        self.drift = drift
        self.transaction_count = 0
        self.authorizations: list[dict[str, object]] = []
        self.completed = 0
        self.reconciled = 0

    @contextmanager
    def transaction(self):
        self.transaction_count += 1
        current = self.transaction_count
        yield object()
        if current == 1:
            if self.drift == "grade":
                self.child.update(
                    grade_code="primary_2",
                    grade_selection_revision=8,
                )
            elif self.drift == "superseded":
                self.plan.update(
                    status="superseded",
                    stage="completed",
                    completed_at=1_001,
                    superseded_at=1_001,
                    lease_token=None,
                    lease_expires_at=None,
                    hard_deadline_at=None,
                    work_unit_kind=None,
                )

    def authorize_shared_build_planning(self, conn, **kwargs):
        self.authorizations.append(
            {
                **kwargs,
                "catalogTransaction": (
                    self.catalog.in_transaction and conn is self.catalog.conn
                ),
            }
        )
        return bool(
            kwargs["plan_id"] == self.plan["id"]
            and kwargs["plan_lease_token"] == self.plan["lease_token"]
            and kwargs["target_fingerprint"]
            == self.plan["target_fingerprint"]
            and int(self.plan.get("lease_expires_at") or 0) > kwargs["now"]
            and int(self.plan.get("hard_deadline_at") or 0) > kwargs["now"]
            and self.plan["status"] == "running"
            and self.plan["stage"] == "planning"
            and self.plan.get("superseded_at") is None
            and self.child["grade_code"] == self.plan["grade_code"]
            and self.child["grade_selection_revision"]
            == self.plan["grade_selection_revision"]
        )

    def complete_shared_build_planning(self, _conn, **kwargs):
        self.completed += 1
        return bool(
            self.authorize_shared_build_planning(object(), **{
                "plan_id": kwargs["plan_id"],
                "plan_lease_token": kwargs["plan_lease_token"],
                "target_fingerprint": kwargs["target_fingerprint"],
                "now": kwargs["now"],
            })
        )

    def reconcile_shared_build(self, _conn, **_kwargs):
        self.reconciled += 1
        return 1


def _service(repository: _CatalogRepository):
    dynamic = _ForbiddenDependency()
    packages = _ForbiddenDependency()
    staged = _ForbiddenDependency()
    return (
        LearningCatalogReleaseService(
            "unused://database",
            dynamic_generation_service=dynamic,
            lesson_package_service=packages,
            staged_content_candidate_generator=staged,
            clock_ms=lambda: 1_001,
            repository=repository,
        ),
        (dynamic, packages, staged),
    )


class LearningPlanningAtomicAuthorityUnitTest(unittest.TestCase):
    def test_grade_or_supersede_after_precheck_persists_no_catalog_authority(self):
        for drift in ("grade", "superseded"):
            with self.subTest(drift=drift):
                catalog = _CatalogRepository()
                preparation = _PlanningRepository(catalog=catalog, drift=drift)
                service, forbidden = _service(catalog)
                adapter = CheckpointSharedBuildAdapter(
                    service,
                    repository=preparation,
                    clock=lambda: 1_001,
                )

                with self.assertRaisesRegex(
                    PreparationDeterministicError,
                    "planning authority is stale",
                ):
                    adapter.advance(
                        copy.deepcopy(preparation.plan),
                        now_ms=1_000,
                        heartbeat=lambda: True,
                    )

                self.assertEqual(len(preparation.authorizations), 2)
                self.assertFalse(preparation.authorizations[0]["catalogTransaction"])
                self.assertTrue(preparation.authorizations[1]["catalogTransaction"])
                self.assertEqual(catalog.create_calls, 0)
                self.assertEqual(catalog.release_reads, 0)
                self.assertEqual(catalog.item_reads, 0)
                self.assertEqual(preparation.completed, 0)
                self.assertEqual(preparation.reconciled, 0)
                self.assertEqual([value.access_count for value in forbidden], [0, 0, 0])

    def test_current_planning_authority_builds_once_and_preserves_handoff(self):
        catalog = _CatalogRepository()
        preparation = _PlanningRepository(catalog=catalog, drift=None)
        service, forbidden = _service(catalog)
        adapter = CheckpointSharedBuildAdapter(
            service,
            repository=preparation,
            clock=lambda: 1_001,
        )

        result = adapter.advance(
            copy.deepcopy(preparation.plan),
            now_ms=1_000,
            heartbeat=lambda: True,
        )

        self.assertEqual(len(preparation.authorizations), 3)
        self.assertFalse(preparation.authorizations[0]["catalogTransaction"])
        self.assertTrue(preparation.authorizations[1]["catalogTransaction"])
        self.assertEqual(catalog.create_calls, 1)
        self.assertEqual(catalog.release_reads, 1)
        self.assertEqual(catalog.item_reads, 1)
        self.assertEqual(preparation.completed, 1)
        self.assertEqual(preparation.reconciled, 1)
        self.assertEqual(result.next_stage, "generating_content")
        self.assertTrue(result.already_persisted)
        self.assertEqual([value.access_count for value in forbidden], [0, 0, 0])

    def test_planning_match_rejects_completed_or_superseded_markers(self):
        target = build_preparation_target("primary_1")
        fingerprint = preparation_target_fingerprint(target)
        plan = _planning_plan()
        child = {
            "id": "child-1",
            "family_id": "family-1",
            "grade_code": "primary_1",
            "grade_selection_revision": 7,
        }
        matches = LearningCurriculumPreparationRepository._planning_authority_matches

        self.assertTrue(
            matches(
                child=child,
                plan=plan,
                plan_lease_token="planning-lease",
                target_fingerprint=fingerprint,
                now=1_001,
            )
        )
        for marker in ("completed_at", "superseded_at"):
            with self.subTest(marker=marker):
                drifted = {**plan, marker: 1_001}
                self.assertFalse(
                    matches(
                        child=child,
                        plan=drifted,
                        plan_lease_token="planning-lease",
                        target_fingerprint=fingerprint,
                        now=1_001,
                    )
                )


if __name__ == "__main__":
    unittest.main()
