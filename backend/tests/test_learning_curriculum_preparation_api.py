from __future__ import annotations

import hashlib
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime
from threading import Event, Lock, get_ident, local
from unittest.mock import patch

from app import create_app
from core.database import Database, DatabaseConnection
from core.errors import ApiError
from repositories.learning_curriculum_preparation_repository import (
    ParentRetryAuthoritySnapshot,
)
from services import learning_curriculum_preparation_service as preparation_module
from services.learning_curriculum_preparation_contract import (
    build_preparation_target,
    preparation_target_fingerprint,
)
from services.learning_catalog_release_service import LearningCatalogReleaseService
from services.service_factory import learning_curriculum_preparation_service
from tests.support import fresh_test_config, request_debug_code


PUBLIC_PREPARATION_KEYS = {
    "schemaVersion",
    "id",
    "childId",
    "gradeCode",
    "gradeLabel",
    "subjects",
    "status",
    "stage",
    "progressPercent",
    "totalCourseCount",
    "readyCourseCount",
    "failedCourseCount",
    "attempt",
    "canRetry",
    "retryAfterMs",
    "message",
    "lastProgressAt",
    "updatedAt",
    "completedAt",
    "error",
}
PREPARATION_SCHEMA_HEADER = "X-Mira-Preparation-Schema"
PREPARATION_SCHEMA_V2 = "mira.learning.preparation.v2"


class _Clock:
    def __init__(self, now_ms: int):
        self.now_ms = now_ms

    def __call__(self) -> int:
        return self.now_ms


class LearningCurriculumPreparationApiTest(unittest.TestCase):
    @staticmethod
    def _retry_lock_label(sql: str) -> str | None:
        normalized = " ".join(sql.split())
        if (
            "FROM learning_curriculum_preparation_plans" in normalized
            and "WHERE id = ? AND family_id = ? LIMIT 1" in normalized
            and not normalized.endswith("FOR UPDATE")
        ):
            return "hint"
        if not normalized.endswith("FOR UPDATE"):
            return None
        locked_sources = (
            ("FROM learning_catalog_releases", "release"),
            ("FROM learning_catalog_build_jobs", "build"),
            ("FROM learning_catalog_build_items", "items"),
            ("FROM learning_catalog_release_items", "release_items"),
            ("FROM learning_course_provider_dispatches", "dispatches"),
            ("FROM learning_course_generation_jobs", "jobs"),
            ("FROM learning_course_generation_candidates", "candidates"),
            ("FROM learning_courses", "courses"),
            ("FROM families WHERE id = ? LIMIT 1", "family"),
            (
                "FROM children WHERE id = ? AND family_id = ? LIMIT 1",
                "child",
            ),
        )
        for source, label in locked_sources:
            if source in normalized:
                return label
        if (
            "FROM learning_curriculum_preparation_plans" in normalized
            and "WHERE id = ? LIMIT 1" in normalized
        ):
            return "plan"
        return None

    def _assert_catalog_retry_lock_order(self, recorded: list[str]) -> None:
        self.assertGreaterEqual(len(recorded), 11, recorded)
        self.assertEqual(recorded[:2], ["hint", "hint"], recorded)
        required_catalog = (
            "release",
            "build",
            "items",
            "release_items",
            "dispatches",
            "jobs",
            "courses",
        )
        positions = {label: recorded.index(label, 2) for label in required_catalog}
        self.assertEqual(
            [positions[label] for label in required_catalog],
            sorted(positions.values()),
            recorded,
        )
        family_index = recorded.index("family", 2)
        child_index = recorded.index("child", family_index + 1)
        plan_index = recorded.index("plan", child_index + 1)
        self.assertLess(max(positions.values()), family_index, recorded)
        if "candidates" in recorded:
            self.assertLess(positions["jobs"], recorded.index("candidates"), recorded)
            self.assertLess(recorded.index("candidates"), positions["courses"], recorded)
        self.assertLess(family_index, child_index, recorded)
        self.assertLess(child_index, plan_index, recorded)

    def setUp(self):
        self.app = create_app(fresh_test_config(CAMERA_RUNTIME_PROVIDER="disabled"))
        self.client = self.app.test_client()
        self.database = Database(self.app.config["DATABASE_URL"])
        self.access_token, self.child_id, self.plan_id = self._create_family_child(
            self.client,
            "13800002401",
            "primary_1",
        )
        with self.database.transaction() as conn:
            plan = conn.execute(
                "SELECT * FROM learning_curriculum_preparation_plans WHERE id = ?",
                (self.plan_id,),
            ).fetchone()
        self.assertIsNotNone(plan)
        self.plan_last_progress_at = int(plan["last_progress_at"])
        self.clock = _Clock(self.plan_last_progress_at)
        clock_patch = patch(
            "services.learning_curriculum_preparation_service.current_time_ms",
            self.clock,
        )
        clock_patch.start()
        self.addCleanup(clock_patch.stop)

    def test_current_returns_exact_parent_contract_and_poll_does_not_mutate_plan(self):
        before = self._plan_row(self.plan_id)
        response = self.client.get(
            "/api/learning/preparations/current",
            query_string={"childId": self.child_id},
            headers=self._auth_headers(),
        )
        after = self._plan_row(self.plan_id)

        self.assertEqual(response.status_code, 200, response.json)
        preparation = response.json["preparation"]
        self.assertEqual(set(preparation), PUBLIC_PREPARATION_KEYS)
        self.assertEqual(preparation["schemaVersion"], "mira.learning.preparation.v1")
        self.assertEqual(preparation["gradeLabel"], "一年级")
        self.assertEqual(
            preparation["subjects"],
            [
                {
                    "code": "chinese",
                    "label": "语文",
                    "readyCourseCount": 0,
                    "failedCourseCount": 0,
                    "totalCourseCount": 12,
                },
                {
                    "code": "math",
                    "label": "数学",
                    "readyCourseCount": 0,
                    "failedCourseCount": 0,
                    "totalCourseCount": 9,
                },
                {
                    "code": "english",
                    "label": "英语",
                    "readyCourseCount": 0,
                    "failedCourseCount": 0,
                    "totalCourseCount": 9,
                },
            ],
        )
        self.assertEqual(preparation["totalCourseCount"], 30)
        self.assertEqual(preparation["retryAfterMs"], 2_500)
        self.assertEqual(
            preparation["message"],
            "系统正在后台准备今日课程",
        )
        self.assertIsNone(preparation["error"])
        self.assertEqual(before["last_progress_at"], after["last_progress_at"])
        self.assertEqual(before["updated_at"], after["updated_at"])

    def test_availability_exposes_active_release_while_preparation_is_not_ready(self):
        latest_plan = self._plan_row(self.plan_id)
        self.assertNotEqual(latest_plan["status"], "ready")

        with patch.object(
            preparation_module,
            "formal_student_release_available",
            return_value=True,
        ):
            response = self.client.get(
                "/api/learning/availability",
                query_string={"childId": self.child_id},
                headers=self._auth_headers(),
            )

        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(
            response.json,
            {
                "ok": True,
                "availability": {
                    "gradeCode": "primary_1",
                    "hasActiveRelease": True,
                    "availableCourseCount": 0,
                    "canLearnNow": True,
                },
            },
        )

    def test_availability_opens_after_the_first_progressive_course(self):
        with patch.object(
            preparation_module,
            "formal_student_release_available",
            return_value=False,
        ), patch(
            "repositories.learning_repository.LearningRepository.student_catalog_summary",
            return_value={
                "catalogStatus": "preparing",
                "availableCourseCount": 1,
                "targetCourseCount": 30,
            },
        ):
            response = self.client.get(
                "/api/learning/availability",
                query_string={"childId": self.child_id},
                headers=self._auth_headers(),
            )

        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(
            response.json["availability"],
            {
                "gradeCode": "primary_1",
                "hasActiveRelease": False,
                "availableCourseCount": 1,
                "canLearnNow": True,
            },
        )

    def test_workspace_access_opens_before_courses_and_preserves_grade_authority(self):
        for grade_code, revision, expected_access in (
            ("primary_1", 1, True),
            ("primary_1", 0, False),
            ("primary_2", 1, False),
            ("kindergarten_middle", 1, False),
        ):
            with self.subTest(grade_code=grade_code, revision=revision):
                with self.database.transaction() as conn:
                    conn.execute(
                        "UPDATE children SET grade_code = ?, grade_selection_revision = ? WHERE id = ?",
                        (grade_code, revision, self.child_id),
                    )
                with patch.object(
                    preparation_module, "formal_student_release_available", return_value=False,
                ), patch(
                    "repositories.learning_repository.LearningRepository.student_catalog_summary",
                    return_value={"availableCourseCount": 0},
                ):
                    response = self.client.get(
                        "/api/learning/availability",
                        query_string={"childId": self.child_id, "includeWorkspaceAccess": "true"},
                        headers=self._auth_headers(),
                    )
                self.assertEqual(response.status_code, 200, response.json)
                availability = response.json["availability"]
                self.assertEqual(availability["canAccessWorkspace"], expected_access)
                self.assertFalse(availability["canLearnNow"])
                self.assertEqual(availability["availableCourseCount"], 0)

    def test_current_authenticates_before_validating_child_id(self):
        missing_auth = self.client.get("/api/learning/preparations/current")
        malformed_auth = self.client.get(
            "/api/learning/preparations/current",
            query_string={"childId": ""},
            headers={"Authorization": "Bearer invalid"},
        )
        authenticated = self.client.get(
            "/api/learning/preparations/current",
            headers=self._auth_headers(),
        )

        self.assertEqual(missing_auth.status_code, 401, missing_auth.json)
        self.assertEqual(malformed_auth.status_code, 401, malformed_auth.json)
        self.assertEqual(authenticated.status_code, 400, authenticated.json)

    def test_schema_negotiation_happens_after_authentication_and_child_ownership(self):
        unauthenticated = self.client.get(
            "/api/learning/preparations/current",
            query_string={"childId": self.child_id},
            headers={PREPARATION_SCHEMA_HEADER: "future.schema"},
        )
        unknown_child = self.client.get(
            "/api/learning/preparations/current",
            query_string={"childId": "child-does-not-exist"},
            headers={
                **self._auth_headers(),
                PREPARATION_SCHEMA_HEADER: "future.schema",
            },
        )
        unknown_schema = self.client.get(
            "/api/learning/preparations/current",
            query_string={"childId": self.child_id},
            headers={
                **self._auth_headers(),
                PREPARATION_SCHEMA_HEADER: "future.schema",
            },
        )

        self.assertEqual(unauthenticated.status_code, 401, unauthenticated.json)
        self.assertEqual(unknown_child.status_code, 404, unknown_child.json)
        self.assertEqual(unknown_schema.status_code, 406, unknown_schema.json)
        self.assertEqual(
            unknown_schema.json["error"],
            "learning_preparation_schema_not_acceptable",
        )
        self.assertEqual(
            unknown_schema.headers.get("Vary"),
            PREPARATION_SCHEMA_HEADER,
        )

    def test_exact_v2_header_returns_v2_and_all_other_present_values_are_406(self):
        accepted = self.client.get(
            "/api/learning/preparations/current",
            query_string={"childId": self.child_id},
            headers={
                **self._auth_headers(),
                PREPARATION_SCHEMA_HEADER: PREPARATION_SCHEMA_V2,
            },
        )

        self.assertEqual(accepted.status_code, 200, accepted.json)
        self.assertEqual(
            accepted.json["preparation"]["schemaVersion"],
            PREPARATION_SCHEMA_V2,
        )
        self.assertIn("contentProgress", accepted.json["preparation"])
        self.assertEqual(
            set(accepted.json["preparation"]),
            PUBLIC_PREPARATION_KEYS | {"contentProgress"},
        )
        self.assertEqual(
            set(accepted.json["preparation"]["contentProgress"]),
            {"candidateCount", "failedCount", "targetCount", "canary"},
        )
        self.assertEqual(
            set(accepted.json["preparation"]["contentProgress"]["canary"]),
            {"candidateCount", "failedCount", "targetCount", "passed"},
        )
        for subject in accepted.json["preparation"]["subjects"]:
            self.assertEqual(
                set(subject),
                {
                    "code",
                    "label",
                    "readyCourseCount",
                    "failedCourseCount",
                    "totalCourseCount",
                    "contentCandidateCount",
                    "contentFailedCount",
                },
            )
        self.assertEqual(
            accepted.headers.get("Vary"),
            PREPARATION_SCHEMA_HEADER,
        )

        for value in (
            "",
            " ",
            "mira.learning.preparation.v1",
            f"{PREPARATION_SCHEMA_V2}, mira.learning.preparation.v1",
            f" {PREPARATION_SCHEMA_V2}",
            f"{PREPARATION_SCHEMA_V2} ",
        ):
            with self.subTest(value=value):
                response = self.client.get(
                    "/api/learning/preparations/current",
                    query_string={"childId": self.child_id},
                    headers={
                        **self._auth_headers(),
                        PREPARATION_SCHEMA_HEADER: value,
                    },
                )
                self.assertEqual(response.status_code, 406, response.json)

    def test_unauthenticated_retry_never_parses_json_or_resolves_provider_profile(self):
        for key in (
            "mira_learning_curriculum_preparation_service",
            "mira_learning_curriculum_preparation_repository",
            "mira_learning_curriculum_preparation_checkpoint_adapter",
        ):
            self.app.extensions.pop(key, None)
        with patch(
            "flask.wrappers.Request.get_json",
            side_effect=AssertionError("body parsed before authentication"),
        ) as get_json, patch(
            "services.service_factory.learning_curriculum_preparation_parent_retry_repository",
            side_effect=AssertionError("retry auditor resolved on public 401"),
        ) as retry_repository, patch(
            "services.service_factory.learning_curriculum_preparation_checkpoint_adapter",
            side_effect=AssertionError("execution adapter resolved on public 401"),
        ) as adapter, patch(
            "services.service_factory._checkpoint_question_phase_profile",
            side_effect=AssertionError("provider profile resolved on public 401"),
        ) as profile, patch(
            "subprocess.Popen",
            side_effect=AssertionError("process started on public 401"),
        ) as process:
            response = self.client.post(
                f"/api/learning/preparations/{self.plan_id}/retry",
                data=b"{malformed",
                content_type="application/json",
                headers={PREPARATION_SCHEMA_HEADER: "future.schema"},
            )

        self.assertEqual(response.status_code, 401, response.json)
        self.assertEqual(get_json.call_count, 0)
        self.assertEqual(retry_repository.call_count, 0)
        self.assertEqual(adapter.call_count, 0)
        self.assertEqual(profile.call_count, 0)
        self.assertEqual(process.call_count, 0)

    def test_retry_ownership_and_schema_precede_json_body_parsing(self):
        for key in (
            "mira_learning_curriculum_preparation_service",
            "mira_learning_curriculum_preparation_parent_retry_repository",
            "mira_learning_curriculum_preparation_checkpoint_adapter",
        ):
            self.app.extensions.pop(key, None)
        with patch(
            "flask.wrappers.Request.get_json",
            side_effect=AssertionError("body parsed before request authority"),
        ) as get_json, patch(
            "services.service_factory.learning_curriculum_preparation_parent_retry_repository",
            side_effect=AssertionError("retry auditor resolved on public 404/406"),
        ) as retry_repository, patch(
            "services.service_factory.learning_curriculum_preparation_checkpoint_adapter",
            side_effect=AssertionError("execution adapter resolved on public 404/406"),
        ) as adapter, patch(
            "services.service_factory._checkpoint_question_phase_profile",
            side_effect=AssertionError("provider profile resolved on public 404/406"),
        ) as profile, patch(
            "subprocess.Popen",
            side_effect=AssertionError("process started on public 404/406"),
        ) as process:
            unknown = self.client.post(
                "/api/learning/preparations/plan-does-not-exist/retry",
                data=b"{malformed",
                content_type="application/json",
                headers={
                    **self._auth_headers(),
                    PREPARATION_SCHEMA_HEADER: "future.schema",
                },
            )
            unsupported = self.client.post(
                f"/api/learning/preparations/{self.plan_id}/retry",
                data=b"{malformed",
                content_type="application/json",
                headers={
                    **self._auth_headers(),
                    PREPARATION_SCHEMA_HEADER: "future.schema",
                },
            )

        self.assertEqual(unknown.status_code, 404, unknown.json)
        self.assertEqual(unsupported.status_code, 406, unsupported.json)
        self.assertEqual(get_json.call_count, 0)
        self.assertEqual(retry_repository.call_count, 0)
        self.assertEqual(adapter.call_count, 0)
        self.assertEqual(profile.call_count, 0)
        self.assertEqual(process.call_count, 0)

    def test_v2_payload_rejects_every_strict_count_or_target_drift(self):
        row = dict(self._plan_row(self.plan_id))
        with self.app.app_context():
            service = learning_curriculum_preparation_service()

        mutations = []
        mutations.append(("row grade target mismatch", {"grade_code": "primary_2"}))
        mutations.append(("bool root count", {"content_candidate_count": True}))
        mutations.append(("root sum drift", {"content_candidate_count": 1}))
        mutations.append(
            (
                "stage progress drift",
                {
                    "stage_progress_json": json.dumps(
                        {
                            "candidateCount": 1,
                            "canaryCandidateCount": 0,
                            "canaryFailedCount": 0,
                            "canaryTargetCount": 3,
                            "failedCount": 0,
                            "targetCount": 30,
                        }
                    )
                },
            )
        )
        subject_progress = json.loads(row["subject_progress_json"])
        subject_progress["chinese"]["contentCandidateCount"] = True
        mutations.append(
            (
                "bool subject count",
                {"subject_progress_json": json.dumps(subject_progress)},
            )
        )
        old_target = build_preparation_target("primary_2")
        mutations.append(
            (
                "target v1 under public v2",
                {
                    "target_spec_json": json.dumps(old_target),
                    "target_fingerprint": preparation_target_fingerprint(old_target),
                },
            )
        )

        for label, mutation in mutations:
            with self.subTest(label=label):
                with self.assertRaises(ApiError) as caught:
                    service.preparation_payload(
                        {**row, **mutation},
                        now_ms=self.clock.now_ms,
                        schema_version=PREPARATION_SCHEMA_V2,
                    )
                self.assertEqual(
                    caught.exception.code,
                    "learning_preparation_state_invalid",
                )

    def test_v2_30_of_30_handoff_and_partial_content_stage_are_frozen(self):
        row = dict(self._plan_row(self.plan_id))
        with self.app.app_context():
            service = learning_curriculum_preparation_service()

        partial_subjects = json.loads(row["subject_progress_json"])
        partial_subjects["chinese"]["contentCandidateCount"] = 1
        partial = {
            **row,
            "status": "running",
            "stage": "generating_content",
            "progress_percent": 6,
            "content_candidate_count": 1,
            "content_canary_candidate_count": 1,
            "stage_progress_json": json.dumps(
                {
                    "candidateCount": 1,
                    "canaryCandidateCount": 1,
                    "canaryFailedCount": 0,
                    "canaryTargetCount": 3,
                    "failedCount": 0,
                    "targetCount": 30,
                }
            ),
            "subject_progress_json": json.dumps(partial_subjects),
        }
        service.preparation_payload(
            partial,
            now_ms=self.clock.now_ms,
            schema_version=PREPARATION_SCHEMA_V2,
        )
        with self.assertRaises(ApiError):
            service.preparation_payload(
                {**partial, "progress_percent": 5},
                now_ms=self.clock.now_ms,
                schema_version=PREPARATION_SCHEMA_V2,
            )

        handoff_subjects = json.loads(row["subject_progress_json"])
        for subject in handoff_subjects.values():
            subject["contentCandidateCount"] = subject["totalCourseCount"]
        handoff = {
            **row,
            "status": "running",
            "stage": "building_classrooms",
            "progress_percent": 35,
            "content_candidate_count": 30,
            "content_canary_candidate_count": 3,
            "content_canary_passed_at": self.clock.now_ms,
            "content_generation_completed_at": self.clock.now_ms,
            "stage_progress_json": json.dumps(
                {
                    "candidateCount": 30,
                    "canaryCandidateCount": 3,
                    "canaryFailedCount": 0,
                    "canaryTargetCount": 3,
                    "failedCount": 0,
                    "targetCount": 30,
                }
            ),
            "subject_progress_json": json.dumps(handoff_subjects),
            "next_run_at": None,
            "completed_at": None,
            "error_code": None,
            "error_message_safe": None,
        }
        service.preparation_payload(
            handoff,
            now_ms=self.clock.now_ms,
            schema_version=PREPARATION_SCHEMA_V2,
        )
        for label, mutation in (
            ("status", {"status": "queued"}),
            ("stage", {"stage": "generating_content"}),
            ("progress", {"progress_percent": 34}),
            ("completion receipt", {"content_generation_completed_at": None}),
            ("formal ready", {"ready_course_count": 1}),
            ("lease", {"lease_token": "unexpected-owner"}),
        ):
            with self.subTest(label=label):
                with self.assertRaises(ApiError):
                    service.preparation_payload(
                        {**handoff, **mutation},
                        now_ms=self.clock.now_ms,
                        schema_version=PREPARATION_SCHEMA_V2,
                    )

    def test_v2_ready_completed_terminal_is_not_rejected_as_content_handoff(self):
        row = dict(self._plan_row(self.plan_id))
        with self.app.app_context():
            service = learning_curriculum_preparation_service()

        subject_progress = json.loads(row["subject_progress_json"])
        for subject in subject_progress.values():
            subject["readyCourseCount"] = subject["totalCourseCount"]
            subject["contentCandidateCount"] = subject["totalCourseCount"]
        content_completed_at = self.clock.now_ms
        ready_at = content_completed_at + 1
        ready = {
            **row,
            "status": "ready",
            "stage": "completed",
            "progress_percent": 100,
            "ready_course_count": 30,
            "failed_course_count": 0,
            "content_target_count": 30,
            "content_candidate_count": 30,
            "content_failed_count": 0,
            "content_canary_target_count": 3,
            "content_canary_candidate_count": 3,
            "content_canary_failed_count": 0,
            "content_canary_passed_at": content_completed_at,
            "content_generation_completed_at": content_completed_at,
            "stage_progress_json": json.dumps(
                {
                    "candidateCount": 30,
                    "canaryCandidateCount": 3,
                    "canaryFailedCount": 0,
                    "canaryTargetCount": 3,
                    "failedCount": 0,
                    "targetCount": 30,
                }
            ),
            "subject_progress_json": json.dumps(subject_progress),
            "classroom_ready_count": 30,
            "speech_ready_count": 30,
            "validation_ready_count": 30,
            "published_course_count": 30,
            "catalog_build_id": "catalog-build-ready",
            "catalog_release_id": "catalog-release-ready",
            "formal_contract_version": "mira.learning.formal-publication.v1",
            "formal_publication_history_id": "grade-release-history-ready",
            "formal_publication_receipt_hash": "a" * 64,
            "formal_ready_at": ready_at,
            "started_at": content_completed_at,
            "completed_at": ready_at,
            "last_progress_at": ready_at,
            "updated_at": ready_at,
            "lease_token": None,
            "lease_expires_at": None,
            "heartbeat_at": None,
            "next_run_at": None,
            "hard_deadline_at": None,
            "resume_stage": None,
            "work_unit_kind": None,
            "bound_catalog_item_id": None,
            "bound_content_attempt_ordinal": None,
            "bound_content_phase": None,
            "retry_reason_code": None,
            "retry_message_safe": None,
            "error_code": None,
            "error_message_safe": None,
            "superseded_at": None,
        }

        payload = service.preparation_payload(
            ready,
            now_ms=ready_at,
            schema_version=PREPARATION_SCHEMA_V2,
        )
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["stage"], "completed")
        self.assertEqual(payload["progressPercent"], 100)
        self.assertEqual(payload["readyCourseCount"], 30)

        for label, mutation in (
            ("progress", {"progress_percent": 99}),
            ("ready count", {"ready_course_count": 29}),
            ("completion time", {"completed_at": None}),
            ("publication receipt", {"formal_publication_receipt_hash": "bad"}),
            ("active lease", {"lease_token": "unexpected-owner"}),
            ("published count", {"published_course_count": 29}),
        ):
            with self.subTest(label=label):
                with self.assertRaises(ApiError) as caught:
                    service.preparation_payload(
                        {**ready, **mutation},
                        now_ms=ready_at,
                        schema_version=PREPARATION_SCHEMA_V2,
                    )
                self.assertEqual(
                    caught.exception.code,
                    "learning_preparation_state_invalid",
                )

        partial_subject_progress = json.loads(ready["subject_progress_json"])
        first_subject = next(iter(partial_subject_progress.values()))
        first_subject["contentCandidateCount"] -= 1
        partial_stage_progress = json.loads(ready["stage_progress_json"])
        partial_stage_progress["candidateCount"] = 29
        internally_consistent_partial_ready = {
            **ready,
            "content_candidate_count": 29,
            "stage_progress_json": json.dumps(partial_stage_progress),
            "subject_progress_json": json.dumps(partial_subject_progress),
        }
        with self.assertRaises(ApiError) as partial_ready_error:
            service.preparation_payload(
                internally_consistent_partial_ready,
                now_ms=ready_at,
                schema_version=PREPARATION_SCHEMA_V2,
            )
        self.assertEqual(
            partial_ready_error.exception.code,
            "learning_preparation_state_invalid",
        )

    def test_parent_retry_decision_is_one_pure_fail_closed_authority(self):
        plan = {
            "status": "failed",
            "stage": "completed",
            "retry_ordinal": 0,
            "error_code": "preparation_dependency_unavailable",
            "error_message_safe": "课程服务暂时不可用，请稍后重试",
            "completed_at": 1234,
            "catalog_build_id": "build-1",
            "catalog_release_id": "release-1",
            "content_candidate_count": 0,
            "content_failed_count": 0,
            "lease_token": None,
            "lease_expires_at": None,
            "heartbeat_at": None,
            "next_run_at": None,
            "hard_deadline_at": None,
            "resume_stage": None,
            "work_unit_kind": None,
            "bound_catalog_item_id": None,
            "bound_content_attempt_ordinal": None,
            "bound_content_phase": None,
            "retry_reason_code": None,
            "retry_message_safe": None,
            "retry_of_plan_id": None,
            "superseded_at": None,
        }
        pre_provider = ParentRetryAuthoritySnapshot(
            authority_class="pre_provider_dependency",
            provider_dispatch_count=0,
            open_or_ambiguous_dispatch_count=0,
            failed_safe_dispatch_count=0,
            provider_graph_complete=False,
            next_work_kind=None,
            build_error_code=None,
        )
        host_only = ParentRetryAuthoritySnapshot(
            authority_class="host_only_dependency",
            provider_dispatch_count=14,
            open_or_ambiguous_dispatch_count=0,
            failed_safe_dispatch_count=0,
            provider_graph_complete=True,
            next_work_kind="host_gate",
            build_error_code=None,
        )
        not_replayable = ParentRetryAuthoritySnapshot(
            authority_class="not_replayable",
            provider_dispatch_count=1,
            open_or_ambiguous_dispatch_count=1,
            failed_safe_dispatch_count=0,
            provider_graph_complete=False,
            next_work_kind=None,
            build_error_code="preparation_provider_dispatch_outcome_unknown",
        )

        decision = preparation_module.parent_retry_decision
        self.assertTrue(decision(plan, pre_provider))
        self.assertTrue(decision(plan, host_only))
        self.assertFalse(decision(plan, not_replayable))
        self.assertFalse(
            decision(
                {**plan, "error_code": "preparation_content_contract_drift"},
                pre_provider,
            )
        )
        self.assertFalse(decision({**plan, "retry_ordinal": 1}, pre_provider))
        self.assertFalse(
            decision(
                plan,
                ParentRetryAuthoritySnapshot(
                    authority_class="pre_provider_dependency",
                    provider_dispatch_count=True,
                    open_or_ambiguous_dispatch_count=0,
                    failed_safe_dispatch_count=0,
                    provider_graph_complete=False,
                    next_work_kind=None,
                    build_error_code=None,
                ),
            )
        )
        for graph_complete in (0, 1, None, "true"):
            with self.subTest(
                authority="pre_provider_dependency",
                graph_complete=graph_complete,
            ):
                self.assertFalse(
                    decision(
                        plan,
                        replace(
                            pre_provider,
                            provider_graph_complete=graph_complete,
                        ),
                    )
                )
            with self.subTest(
                authority="host_only_dependency",
                graph_complete=graph_complete,
            ):
                self.assertFalse(
                    decision(
                        plan,
                        replace(
                            host_only,
                            provider_graph_complete=graph_complete,
                        ),
                    )
                )
        self.assertFalse(
            decision(
                plan,
                ParentRetryAuthoritySnapshot(
                    authority_class="host_only_dependency",
                    provider_dispatch_count=-1,
                    open_or_ambiguous_dispatch_count=0,
                    failed_safe_dispatch_count=0,
                    provider_graph_complete=True,
                    next_work_kind="host_gate",
                    build_error_code=None,
                ),
            )
        )

    def test_unknown_and_other_family_children_have_identical_404_bodies(self):
        other_client = self.app.test_client()
        _, other_child_id, _ = self._create_family_child(
            other_client,
            "13800002402",
            "primary_1",
        )
        unknown = self.client.get(
            "/api/learning/preparations/current",
            query_string={"childId": "child-does-not-exist"},
            headers=self._auth_headers(),
        )
        other_family = self.client.get(
            "/api/learning/preparations/current",
            query_string={"childId": other_child_id},
            headers=self._auth_headers(),
        )

        self.assertEqual(unknown.status_code, 404, unknown.json)
        self.assertEqual(other_family.status_code, 404, other_family.json)
        self.assertEqual(unknown.json, other_family.json)

    def test_non_primary_and_valid_primary_without_plan_both_fail_closed_as_null(self):
        with self.database.transaction() as conn:
            conn.execute(
                "DELETE FROM learning_curriculum_preparation_plans WHERE id = ?",
                (self.plan_id,),
            )
        no_plan = self.client.get(
            "/api/learning/preparations/current",
            query_string={"childId": self.child_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(no_plan.status_code, 200, no_plan.json)
        self.assertEqual(no_plan.json, {"ok": True, "preparation": None})

        with self.database.transaction() as conn:
            conn.execute(
                "UPDATE children SET grade_code = 'kindergarten_middle' WHERE id = ?",
                (self.child_id,),
            )
        non_primary = self.client.get(
            "/api/learning/preparations/current",
            query_string={"childId": self.child_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(non_primary.status_code, 200, non_primary.json)
        self.assertEqual(non_primary.json, {"ok": True, "preparation": None})

    def test_unopened_primary_grade_returns_exact_unavailable_envelope(self):
        with self.database.transaction() as conn:
            conn.execute(
                "UPDATE children SET grade_code = 'primary_2' WHERE id = ?",
                (self.child_id,),
            )

        response = self.client.get(
            "/api/learning/preparations/current",
            query_string={"childId": self.child_id},
            headers=self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(
            response.json,
            {
                "ok": True,
                "preparation": None,
                "learningPreparationAvailability": {
                    "status": "unavailable",
                    "gradeCode": "primary_2",
                    "message": "该年级正式课程尚未开放",
                },
            },
        )

    def test_retry_backoff_uses_only_last_progress_and_null_is_stale(self):
        cases = (
            (0, 2_500),
            (4_999, 2_500),
            (5_000, 5_000),
            (14_999, 5_000),
            (15_000, 10_000),
            (29_999, 10_000),
            (30_000, 20_000),
            (59_999, 20_000),
            (60_000, 30_000),
            (125_000, 30_000),
        )
        for age, expected in cases:
            with self.subTest(age=age):
                self.clock.now_ms = self.plan_last_progress_at + age
                response = self._get_current()
                self.assertEqual(response.status_code, 200, response.json)
                self.assertEqual(response.json["preparation"]["retryAfterMs"], expected)

        self.clock.now_ms = self.plan_last_progress_at + 125_000
        with self.database.transaction() as conn:
            conn.execute(
                "UPDATE learning_curriculum_preparation_plans "
                "SET last_progress_at = NULL, updated_at = ? WHERE id = ?",
                (self.clock.now_ms, self.plan_id),
            )
        null_progress = self._get_current()
        self.assertEqual(
            null_progress.json["preparation"]["retryAfterMs"],
            30_000,
        )

    def test_internal_stages_share_one_silent_parent_message(self):
        row = dict(self._plan_row(self.plan_id))
        historical_target = json.loads(str(row["target_spec_json"]))
        historical_target["schemaVersion"] = "mira.learning.preparation-target.v1"
        with self.app.app_context():
            service = learning_curriculum_preparation_service()
        speech = service.preparation_payload(
            {
                **row,
                "target_spec_json": json.dumps(historical_target),
                "status": "running",
                "stage": "generating_speech",
            },
            now_ms=self.clock.now_ms,
        )
        self.assertEqual(
            speech["message"],
            "系统正在后台准备今日课程",
        )

        waiting = service.preparation_payload(
            {
                **row,
                "target_spec_json": json.dumps(historical_target),
                "status": "queued",
                "stage": "retry_wait",
            },
            now_ms=self.clock.now_ms,
        )
        self.assertEqual(
            waiting["message"],
            "系统正在后台准备今日课程",
        )

    def test_failed_payload_uses_allowlisted_error_with_generic_fallback(self):
        self._mark_failed(
            self.plan_id,
            error_code="../../prompt/provider/api_key",
            error_message="/private/secret prompt Bearer abc provider api_key=hunter2",
        )
        response = self._get_current()

        self.assertEqual(response.status_code, 200, response.json)
        preparation = response.json["preparation"]
        self.assertEqual(set(preparation), PUBLIC_PREPARATION_KEYS)
        self.assertEqual(
            preparation["error"],
            {
                "code": "preparation_failed",
                "message": "课程准备暂时失败，请稍后重试",
            },
        )
        serialized = json.dumps(response.json, ensure_ascii=False)
        for fragment in ("private", "secret", "prompt", "provider", "hunter2", "api_key"):
            self.assertNotIn(fragment, serialized.lower())
        self.assertIsNone(preparation["retryAfterMs"])

    def test_known_error_code_maps_to_parent_safe_message_not_stored_message(self):
        self._mark_failed(
            self.plan_id,
            error_code="preparation_stage_deadline_exceeded",
            error_message="/tmp/build/prompt.txt Provider timed out with secret",
        )
        response = self._get_current()
        self.assertEqual(
            response.json["preparation"]["error"],
            {
                "code": "preparation_stage_deadline_exceeded",
                "message": "课程准备时间较长，请重新准备",
            },
        )

    def test_retry_body_is_exact_untrimmed_ascii_contract_and_authentication_is_first(self):
        self._mark_failed(self.plan_id)
        invalid_bodies = (
            None,
            [],
            "parent-retry-1",
            True,
            {},
            {"requestId": "parent-retry-1", "extra": True},
            {"requestId": True},
            {"requestId": ""},
            {"requestId": " parent-retry-1"},
            {"requestId": "parent-retry-1 "},
            {"requestId": "重试-1"},
            {"requestId": "a" * 129},
        )
        for body in invalid_bodies:
            with self.subTest(body=body):
                response = self.client.post(
                    f"/api/learning/preparations/{self.plan_id}/retry",
                    json=body,
                    headers=self._auth_headers(),
                )
                self.assertEqual(response.status_code, 400, response.json)

        unauthenticated = self.client.post(
            f"/api/learning/preparations/{self.plan_id}/retry",
            json=["malformed"],
        )
        self.assertEqual(unauthenticated.status_code, 401, unauthenticated.json)

    def test_retry_is_idempotent_and_different_key_cannot_consume_another_retry(self):
        self._mark_failed(self.plan_id)
        first = self._retry(self.plan_id, "parent-retry-1")
        replay = self._retry(self.plan_id, "parent-retry-1")
        other_key = self._retry(self.plan_id, "parent-retry-2")

        self.assertEqual(first.status_code, 202, first.json)
        self.assertEqual(replay.status_code, 200, replay.json)
        self.assertEqual(
            first.json["preparation"]["id"],
            replay.json["preparation"]["id"],
        )
        self.assertEqual(other_key.status_code, 409, other_key.json)
        self.assertEqual(first.json["preparation"]["attempt"], 2)
        self.assertFalse(first.json["preparation"]["canRetry"])
        self.assertEqual(set(first.json["preparation"]), PUBLIC_PREPARATION_KEYS)

    def test_retry_post_exact_v2_success_and_unsupported_schema_vary(self):
        self._mark_failed(self.plan_id)
        unsupported = self.client.post(
            f"/api/learning/preparations/{self.plan_id}/retry",
            json={"requestId": "parent-retry-v2"},
            headers={
                **self._auth_headers(),
                PREPARATION_SCHEMA_HEADER: "future.schema",
            },
        )
        accepted = self.client.post(
            f"/api/learning/preparations/{self.plan_id}/retry",
            json={"requestId": "parent-retry-v2"},
            headers={
                **self._auth_headers(),
                PREPARATION_SCHEMA_HEADER: PREPARATION_SCHEMA_V2,
            },
        )

        self.assertEqual(unsupported.status_code, 406, unsupported.json)
        self.assertEqual(
            unsupported.json["error"],
            "learning_preparation_schema_not_acceptable",
        )
        self.assertEqual(
            unsupported.headers.get("Vary"),
            PREPARATION_SCHEMA_HEADER,
        )
        self.assertEqual(accepted.status_code, 202, accepted.json)
        self.assertEqual(
            accepted.headers.get("Vary"),
            PREPARATION_SCHEMA_HEADER,
        )
        preparation = accepted.json["preparation"]
        self.assertEqual(
            set(preparation),
            PUBLIC_PREPARATION_KEYS | {"contentProgress"},
        )
        self.assertEqual(preparation["schemaVersion"], PREPARATION_SCHEMA_V2)
        self.assertEqual(
            set(preparation["contentProgress"]),
            {"candidateCount", "failedCount", "targetCount", "canary"},
        )
        self.assertEqual(
            set(preparation["contentProgress"]["canary"]),
            {"candidateCount", "failedCount", "targetCount", "passed"},
        )
        self.assertEqual(preparation["contentProgress"]["targetCount"], 30)
        for subject in preparation["subjects"]:
            self.assertEqual(
                set(subject),
                {
                    "code",
                    "label",
                    "readyCourseCount",
                    "failedCourseCount",
                    "totalCourseCount",
                    "contentCandidateCount",
                    "contentFailedCount",
                },
            )

    def test_replay_revalidates_the_failed_original_status(self):
        self._mark_failed(self.plan_id)
        created = self._retry(self.plan_id, "parent-retry-status")
        self.assertEqual(created.status_code, 202, created.json)
        with self.database.transaction() as conn:
            conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET status = 'superseded', error_code = NULL,
                  error_message_safe = NULL, superseded_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (self.clock.now_ms, self.clock.now_ms, self.plan_id),
            )

        replay = self._retry(self.plan_id, "parent-retry-status")
        self.assertEqual(replay.status_code, 409, replay.json)

    def test_retry_rejects_non_failed_retry_successor_and_no_longer_current_source(self):
        queued = self._retry(self.plan_id, "parent-retry-queued")
        self.assertEqual(queued.status_code, 409, queued.json)

        self._mark_failed(self.plan_id)
        changed = self.client.patch(
            f"/api/children/{self.child_id}",
            json={
                "gradeCode": "primary_2",
                "schoolYearStartYear": datetime.now().year,
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(changed.status_code, 200, changed.json)
        no_longer_current = self._retry(self.plan_id, "parent-retry-old-grade")
        self.assertEqual(no_longer_current.status_code, 409, no_longer_current.json)

    def test_retry_rejects_a_legacy_failed_plan_for_an_unopened_primary_grade(self):
        target = build_preparation_target("primary_2")
        fingerprint = preparation_target_fingerprint(target)

        class Transaction:
            def __enter__(inner_self):
                return inner_self

            def __exit__(inner_self, exc_type, exc, traceback):
                return False

        class HintRepository:
            def transaction(inner_self):
                return Transaction()

            def get_plan_for_family(inner_self, conn, *, family_id, plan_id):
                return {"id": plan_id, "grade_code": "primary_2"}

        source = {
            "id": "legacy-primary-2-plan",
            "family_id": "family-1",
            "child_id": "child-1",
            "grade_code": "primary_2",
            "school_year_start_year": 2026,
            "grade_selection_revision": 1,
            "target_fingerprint": fingerprint,
        }

        class RetryRepository:
            def transaction(inner_self):
                return Transaction()

            def lock_parent_retry_context(
                inner_self, conn, *, family_id, plan_id
            ):
                return (
                    {
                        "id": "child-1",
                        "grade_code": "primary_2",
                        "grade_school_year_start": 2026,
                        "grade_selection_revision": 1,
                    },
                    source,
                    object(),
                )

            def get_current_for_child(inner_self, *args, **kwargs):
                raise AssertionError(
                    "unopened grade reached retry successor resolution"
                )

        class AuthService:
            @staticmethod
            def authenticate(access_token):
                return {"family": {"id": "family-1"}}

        service = preparation_module.LearningCurriculumPreparationService(
            self.app.config["DATABASE_URL"],
            auth_service=AuthService(),
            repository=HintRepository(),
            retry_repository_factory=RetryRepository,
        )

        with patch.object(preparation_module, "parent_retry_decision", return_value=True):
            with self.assertRaises(ApiError) as caught:
                service.retry(
                    "access-token",
                    source["id"],
                    lambda: {"requestId": "parent-retry-unopened-grade"},
                )

        self.assertEqual(caught.exception.code, "learning_preparation_not_retryable")

    def test_retry_rejects_live_school_year_drift(self):
        self._mark_failed(self.plan_id)
        with self.database.transaction() as conn:
            conn.execute(
                """
                UPDATE children
                SET grade_school_year_start = grade_school_year_start + 1
                WHERE id = ?
                """,
                (self.child_id,),
            )

        response = self._retry(self.plan_id, "parent-retry-old-school-year")
        self.assertEqual(response.status_code, 409, response.json)

    def test_unknown_and_other_family_plans_have_identical_404_bodies(self):
        other_client = self.app.test_client()
        other_token, _, other_plan_id = self._create_family_child(
            other_client,
            "13800002403",
            "primary_1",
        )
        self._mark_failed(other_plan_id)
        unknown = self._retry("plan-does-not-exist", "parent-retry-1")
        other_family = self._retry(other_plan_id, "parent-retry-1")

        self.assertEqual(unknown.status_code, 404, unknown.json)
        self.assertEqual(other_family.status_code, 404, other_family.json)
        self.assertEqual(unknown.json, other_family.json)
        self.assertIsNotNone(other_token)

    def test_same_client_request_id_is_scoped_to_family_and_failed_plan(self):
        other_client = self.app.test_client()
        other_token, _, other_plan_id = self._create_family_child(
            other_client,
            "13800002404",
            "primary_1",
        )
        self._mark_failed(self.plan_id)
        self._mark_failed(other_plan_id)

        first = self._retry(self.plan_id, "same-client-key")
        second = other_client.post(
            f"/api/learning/preparations/{other_plan_id}/retry",
            json={"requestId": "same-client-key"},
            headers=self._auth_headers(other_token),
        )
        self.assertEqual(first.status_code, 202, first.json)
        self.assertEqual(second.status_code, 202, second.json)
        with self.database.transaction() as conn:
            rows = conn.execute(
                """
                SELECT family_id, request_id
                FROM learning_curriculum_preparation_plans
                WHERE retry_ordinal = 1
                ORDER BY family_id
                """
            ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({row["request_id"] for row in rows}), 2)
        source_plan_by_family = {
            self._plan_row(self.plan_id)["family_id"]: self.plan_id,
            self._plan_row(other_plan_id)["family_id"]: other_plan_id,
        }
        for row in rows:
            expected = hashlib.sha256(
                f"{row['family_id']}|{source_plan_by_family[row['family_id']]}|"
                "same-client-key".encode("utf-8")
            ).hexdigest()
            self.assertEqual(row["request_id"], f"grade-prep-retry:{expected}")

    def test_concurrent_same_key_has_one_created_response_and_one_replay(self):
        self._mark_failed(self.plan_id)
        responses, connection_ids, lock_orders = self._concurrent_retries(
            ("race-key", "race-key")
        )
        self.assertEqual(len(set(connection_ids)), 2, connection_ids)
        for connection_id in set(connection_ids):
            self._assert_catalog_retry_lock_order(lock_orders[connection_id])
        self.assertEqual(sorted(response.status_code for response in responses), [200, 202])
        self.assertEqual(
            len({response.json["preparation"]["id"] for response in responses}),
            1,
        )

    def test_concurrent_different_keys_has_one_created_response_and_one_conflict(self):
        self._mark_failed(self.plan_id)
        responses, connection_ids, lock_orders = self._concurrent_retries(
            ("race-key-a", "race-key-b")
        )
        self.assertEqual(len(set(connection_ids)), 2, connection_ids)
        for connection_id in set(connection_ids):
            self._assert_catalog_retry_lock_order(lock_orders[connection_id])
        self.assertEqual(sorted(response.status_code for response in responses), [202, 409])

    def test_retry_lock_order_is_hint_then_family_child_plan(self):
        self._mark_failed(self.plan_id)
        thread_state = local()
        recorded: list[str] = []
        recorded_lock = Lock()
        original_execute = DatabaseConnection.execute

        def record_order(connection, sql: str, params=()):
            label = self._retry_lock_label(sql)
            result = original_execute(connection, sql, params)
            if label and getattr(thread_state, "active", False):
                with recorded_lock:
                    recorded.append(label)
            return result

        thread_state.active = True
        with patch.object(DatabaseConnection, "execute", record_order):
            response = self._retry(self.plan_id, "lock-order-key")
        thread_state.active = False

        self.assertEqual(response.status_code, 202, response.json)
        self._assert_catalog_retry_lock_order(recorded)

    def _get_current(self):
        return self.client.get(
            "/api/learning/preparations/current",
            query_string={"childId": self.child_id},
            headers=self._auth_headers(),
        )

    def _retry(self, plan_id: str, request_id: str):
        return self.client.post(
            f"/api/learning/preparations/{plan_id}/retry",
            json={"requestId": request_id},
            headers=self._auth_headers(),
        )

    def _concurrent_retries(self, request_ids: tuple[str, str]):
        both_hints_reached = Event()
        allow_family_locks = Event()
        evidence_lock = Lock()
        first_hint_connection_by_thread: dict[int, int] = {}
        lock_orders_by_thread: dict[int, list[str]] = {}
        original_execute = DatabaseConnection.execute

        def mysql_connection_id(connection: DatabaseConnection) -> int:
            row = original_execute(
                connection,
                "SELECT CONNECTION_ID() AS connection_id",
            ).fetchone()
            return int(row["connection_id"])

        def record_overlap(connection, sql: str, params=()):
            label = self._retry_lock_label(sql)
            is_hint = label == "hint"

            if is_hint:
                result = original_execute(connection, sql, params)
                thread_id = get_ident()
                connection_id = mysql_connection_id(connection)
                with evidence_lock:
                    lock_orders_by_thread.setdefault(thread_id, []).append("hint")
                    first_hint_connection_by_thread.setdefault(
                        thread_id, connection_id
                    )
                    if len(first_hint_connection_by_thread) == 2:
                        both_hints_reached.set()
                if not allow_family_locks.wait(timeout=12):
                    raise AssertionError(
                        "concurrent retry timed out before family locks were released"
                    )
                return result

            if label is not None:
                thread_id = get_ident()
                with evidence_lock:
                    order = lock_orders_by_thread.setdefault(thread_id, [])
                    order.append(label)
            return original_execute(connection, sql, params)

        def retry_once(request_id: str):
            client = self.app.test_client()
            return client.post(
                f"/api/learning/preparations/{self.plan_id}/retry",
                json={"requestId": request_id},
                headers=self._auth_headers(),
            )

        coordination_error: AssertionError | None = None
        responses = []
        future_error: BaseException | None = None
        with patch.object(DatabaseConnection, "execute", record_overlap):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(retry_once, value) for value in request_ids]
                if not both_hints_reached.wait(timeout=10):
                    coordination_error = AssertionError(
                        "both concurrent retries did not reach the source hint boundary"
                    )
                else:
                    with evidence_lock:
                        connection_ids = tuple(
                            first_hint_connection_by_thread.values()
                        )
                        if len(set(connection_ids)) != 2:
                            coordination_error = AssertionError(
                                "concurrent retries did not use two distinct MySQL connections: "
                                f"{connection_ids}"
                            )
                allow_family_locks.set()
                for future in futures:
                    try:
                        responses.append(future.result(timeout=15))
                    except BaseException as exc:  # pragma: no cover - failure evidence
                        if future_error is None:
                            future_error = exc

        if coordination_error is not None:
            raise coordination_error
        if future_error is not None:
            raise future_error
        with evidence_lock:
            connection_order_pairs = [
                (
                    connection_id,
                    list(lock_orders_by_thread[thread_id]),
                )
                for thread_id, connection_id
                in first_hint_connection_by_thread.items()
            ]
            return (
                responses,
                tuple(pair[0] for pair in connection_order_pairs),
                {pair[0]: pair[1] for pair in connection_order_pairs},
            )

    def _mark_failed(
        self,
        plan_id: str,
        *,
        error_code: str = "preparation_dependency_unavailable",
        error_message: str = "stored internal detail",
    ) -> None:
        failed_at = self.clock.now_ms
        source = self._plan_row(plan_id)
        target = json.loads(str(source["target_spec_json"]))
        catalog = LearningCatalogReleaseService(
            self.app.config["DATABASE_URL"],
            dynamic_generation_service=None,
            lesson_package_service=None,
        )
        catalog_payload = catalog.create_preparation_content_build(
            request_id=str(source["shared_build_request_id"]),
            title="Task 9 parent retry authority",
            preparation_target=target,
            target_fingerprint=str(source["target_fingerprint"]),
        )
        build_id = str(catalog_payload["build"]["id"])
        release_id = str(catalog_payload["release"]["id"])
        progress = {
            "chinese": {
                "totalCourseCount": 12,
                "readyCourseCount": 0,
                "failedCourseCount": 12,
                "contentCandidateCount": 0,
                "contentFailedCount": 0,
            },
            "math": {
                "totalCourseCount": 9,
                "readyCourseCount": 0,
                "failedCourseCount": 9,
                "contentCandidateCount": 0,
                "contentFailedCount": 0,
            },
            "english": {
                "totalCourseCount": 9,
                "readyCourseCount": 0,
                "failedCourseCount": 9,
                "contentCandidateCount": 0,
                "contentFailedCount": 0,
            },
        }
        with self.database.transaction() as conn:
            conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET status = 'failed', stage = 'completed',
                  catalog_build_id = ?, catalog_release_id = ?,
                  ready_course_count = 0, failed_course_count = total_course_count,
                  subject_progress_json = ?, next_run_at = NULL,
                  lease_token = NULL, lease_expires_at = NULL, heartbeat_at = NULL,
                  hard_deadline_at = NULL, resume_stage = NULL,
                  error_code = ?, error_message_safe = ?, completed_at = ?,
                  updated_at = ?
                WHERE id = ?
                """,
                (
                    build_id,
                    release_id,
                    json.dumps(progress, ensure_ascii=False),
                    error_code,
                    error_message,
                    failed_at,
                    failed_at,
                    plan_id,
                ),
            )

    def _plan_row(self, plan_id: str):
        with self.database.transaction() as conn:
            return conn.execute(
                "SELECT * FROM learning_curriculum_preparation_plans WHERE id = ?",
                (plan_id,),
            ).fetchone()

    def _create_family_child(self, client, phone: str, grade_code: str):
        code = request_debug_code(client, phone)
        login = client.post(
            "/api/auth/sms/login",
            json={"phone": phone, "code": code},
        )
        self.assertEqual(login.status_code, 200, login.json)
        token = login.json["tokens"]["accessToken"]
        parent = client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "家长",
                "relationship": "家长",
                "relationshipKey": "other",
            },
            headers=self._auth_headers(token),
        )
        self.assertEqual(parent.status_code, 200, parent.json)
        child = client.post(
            "/api/setup/child",
            json={
                "name": f"{grade_code}孩子",
                "nickname": f"{grade_code}孩子",
                "gradeCode": grade_code,
                "schoolYearStartYear": datetime.now().year,
            },
            headers=self._auth_headers(token),
        )
        self.assertEqual(child.status_code, 200, child.json)
        return (
            token,
            child.json["child"]["id"],
            child.json["learningPreparation"]["id"],
        )

    def _auth_headers(self, token: str | None = None) -> dict[str, str]:
        return {"Authorization": f"Bearer {token or self.access_token}"}


if __name__ == "__main__":
    unittest.main()
