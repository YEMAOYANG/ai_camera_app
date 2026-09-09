from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
import unittest
from unittest.mock import patch

import pymysql

from core.database import Database
from repositories.learning_curriculum_preparation_repository import (
    LearningCurriculumPreparationConflict,
    LearningCurriculumPreparationRepository,
)
from repositories.profile_repository import ProfileRepository
from scripts.migrate import run_migrations
from services.learning_curriculum_preparation_contract import (
    TARGET_SCHEMA_V1,
    build_preparation_target,
    preparation_target_fingerprint,
)
from tests.support import fresh_test_config


MIGRATION_VERSION = "054_learning_curriculum_preparations.sql"
RUNNER_MIGRATION_VERSION = "055_learning_curriculum_preparation_runner_evidence.sql"
CONTENT_STAGE_MIGRATION_VERSION = (
    "056_learning_curriculum_preparation_content_stage.sql"
)


class LearningCurriculumPreparationRepositoryTest(unittest.TestCase):
    def setUp(self):
        config = fresh_test_config()
        self.database_url = config["DATABASE_URL"]
        self.assertIn("/ai_camera_app_test", self.database_url)
        self.assertNotIn("/ai_camera_app_dev", self.database_url)
        self.database = Database(self.database_url)
        self.repository = LearningCurriculumPreparationRepository(self.database)
        self.target = build_preparation_target("primary_1")
        self.fingerprint = preparation_target_fingerprint(self.target)
        with self.database.transaction() as conn:
            self._insert_family_child(conn, "fam_1", "child_1")
            self._insert_family_child(conn, "fam_2", "child_2")

    def test_same_revision_and_target_returns_one_plan(self):
        with self.repository.transaction() as conn:
            first, first_created = self._reserve(conn, now=1000)
            second, second_created = self._reserve(conn, now=1001)

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["next_run_at"], 1000)
        self.assertEqual(first["last_progress_at"], 1000)
        self.assertIsNone(first["hard_deadline_at"])
        self.assertIsNone(first["lease_token"])
        self.assertEqual(
            list(json.loads(first["subject_progress_json"])),
            ["chinese", "math", "english"],
        )
        self.assertEqual(
            json.loads(first["subject_progress_json"]),
            {
                "chinese": {
                    "totalCourseCount": 12,
                    "readyCourseCount": 0,
                    "failedCourseCount": 0,
                    "contentCandidateCount": 0,
                    "contentFailedCount": 0,
                },
                "math": {
                    "totalCourseCount": 9,
                    "readyCourseCount": 0,
                    "failedCourseCount": 0,
                    "contentCandidateCount": 0,
                    "contentFailedCount": 0,
                },
                "english": {
                    "totalCourseCount": 9,
                    "readyCourseCount": 0,
                    "failedCourseCount": 0,
                    "contentCandidateCount": 0,
                    "contentFailedCount": 0,
                },
            },
        )

    def test_v2_release_retains_retry_evidence_and_does_not_extend_deadline(self):
        with self.repository.transaction() as conn:
            initial, _ = self._reserve(conn, request_id="release-v2-lease", now=1000)
            claimed = self.repository.claim_next(conn, now=1000, lease_ms=60_000)
            self.assertFalse(self.repository.release_lease(conn, plan_id=initial['id'],
                lease_token='wrong-token', expected_stage='planning', now=1001))
            self.assertTrue(self.repository.release_lease(conn, plan_id=initial['id'],
                lease_token=claimed['lease_token'], expected_stage='planning', now=1002))
            waiting = self.repository.get_plan(conn, initial['id'])
            self.assertEqual(waiting['status'], 'queued')
            self.assertEqual(waiting['stage'], 'retry_wait')
            self.assertEqual(waiting['work_unit_kind'], 'coordinator')
            self.assertEqual(waiting['retry_reason_code'], 'preparation_dependency_unavailable')
            self.assertIsNone(waiting['lease_token'])
            self.assertEqual(waiting['hard_deadline_at'], claimed['hard_deadline_at'])
            reclaimed = self.repository.claim_next(conn, now=1003, lease_ms=60_000)
            self.assertTrue(self.repository.release_lease(conn, plan_id=initial['id'],
                lease_token=reclaimed['lease_token'], expected_stage='planning',
                now=reclaimed['hard_deadline_at'] + 1000))
            expired = self.repository.get_plan(conn, initial['id'])
            self.assertEqual(expired['hard_deadline_at'], reclaimed['hard_deadline_at'])
            self.assertEqual(expired['next_run_at'], reclaimed['hard_deadline_at'])

    def test_v2_initial_claim_dependency_retry_and_terminal_evidence_shape(self):
        with self.database.transaction() as conn:
            marker = conn.execute(
                "SELECT COUNT(*) AS count FROM schema_migrations WHERE version = ?",
                (CONTENT_STAGE_MIGRATION_VERSION,),
            ).fetchone()
        self.assertEqual(marker["count"], 1)

        with self.repository.transaction() as conn:
            initial, _ = self._reserve(
                conn, request_id="v2-content-state-shapes", now=1400
            )
            claimed = self.repository.claim_next(
                conn,
                now=1400,
                lease_ms=60_000,
                stage_deadline_ms={"planning": 120_000},
            )
            self.assertTrue(
                self.repository.defer_claim(
                    conn,
                    plan_id=initial["id"],
                    lease_token=claimed["lease_token"],
                    target_fingerprint=self.fingerprint,
                    expected_stage="planning",
                    next_run_at=1401,
                    error_code="preparation_dependency_unavailable",
                    now=1401,
                )
            )
            waiting = self.repository.get_plan(conn, initial["id"])
            reclaimed = self.repository.claim_next(
                conn,
                now=1401,
                lease_ms=60_000,
                stage_deadline_ms={"planning": 120_000},
            )
            self.assertTrue(
                self.repository.fail_claim(
                    conn,
                    plan_id=initial["id"],
                    lease_token=reclaimed["lease_token"],
                    target_fingerprint=self.fingerprint,
                    expected_stage="planning",
                    error_code="preparation_dependency_unavailable",
                    error_message_safe="课程服务暂时不可用，请稍后重试",
                    now=1402,
                )
            )
            failed = self.repository.get_plan(conn, initial["id"])

        self.assertEqual(initial["content_target_count"], 30)
        self.assertEqual(initial["content_canary_target_count"], 3)
        self.assertEqual(initial["content_candidate_count"], 0)
        self.assertEqual(initial["content_failed_count"], 0)
        self.assertEqual(
            json.loads(initial["stage_progress_json"]),
            {
                "candidateCount": 0,
                "canaryCandidateCount": 0,
                "canaryFailedCount": 0,
                "canaryTargetCount": 3,
                "failedCount": 0,
                "targetCount": 30,
            },
        )
        self.assertEqual(claimed["work_unit_kind"], "coordinator")
        self.assertIsNone(claimed["bound_catalog_item_id"])
        self.assertEqual(waiting["work_unit_kind"], "coordinator")
        self.assertEqual(
            waiting["retry_reason_code"], "preparation_dependency_unavailable"
        )
        self.assertEqual(
            waiting["retry_message_safe"],
            "课程服务暂时不可用，请稍后重试",
        )
        self.assertIsNone(reclaimed["retry_reason_code"])
        self.assertIsNone(reclaimed["retry_message_safe"])
        for field in (
            "work_unit_kind",
            "bound_catalog_item_id",
            "bound_content_attempt_ordinal",
            "bound_content_phase",
            "retry_reason_code",
            "retry_message_safe",
        ):
            self.assertIsNone(failed[field], field)

    def test_v2_fresh_coordinator_claim_has_exact_two_minute_budget_and_cap(self):
        with self.repository.transaction() as conn:
            initial, _ = self._reserve(
                conn, request_id="v2-exact-coordinator-budget", now=2_000
            )
            claimed = self.repository.claim_next(
                conn,
                now=2_000,
                lease_ms=300_000,
                stage_deadline_ms={"planning": 900_000},
            )

        self.assertEqual(claimed["id"], initial["id"])
        self.assertEqual(claimed["work_unit_kind"], "coordinator")
        self.assertEqual(claimed["hard_deadline_at"], 122_000)
        self.assertEqual(claimed["lease_expires_at"], 122_000)

    def test_runner_count_and_claim_ignore_older_grade_and_stale_fingerprint(self):
        primary_two_target = build_preparation_target("primary_2")
        primary_two_fingerprint = preparation_target_fingerprint(
            primary_two_target
        )
        with self.repository.transaction() as conn:
            self._insert_family_child(conn, "fam_scope_stale", "child_scope_stale")
            self._insert_family_child(conn, "fam_scope_exact", "child_scope_exact")
            primary_two, _ = self.repository.reserve_plan(
                conn,
                family_id="fam_2",
                child_id="child_2",
                grade_code="primary_2",
                school_year_start_year=2026,
                grade_selection_revision=2,
                target=primary_two_target,
                target_fingerprint=primary_two_fingerprint,
                request_id="scope-primary-two",
                shared_build_request_id=f"grade-build:{primary_two_fingerprint}",
                now=1_000,
            )
            stale, _ = self.repository.reserve_plan(
                conn,
                family_id="fam_scope_stale",
                child_id="child_scope_stale",
                grade_code="primary_1",
                school_year_start_year=2026,
                grade_selection_revision=1,
                target=self.target,
                target_fingerprint=self.fingerprint,
                request_id="scope-primary-one-stale",
                shared_build_request_id=f"grade-build:{self.fingerprint}",
                now=1_001,
            )
            conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET target_fingerprint = ? WHERE id = ?
                """,
                ("0" * 64, stale["id"]),
            )
            exact, _ = self.repository.reserve_plan(
                conn,
                family_id="fam_scope_exact",
                child_id="child_scope_exact",
                grade_code="primary_1",
                school_year_start_year=2026,
                grade_selection_revision=1,
                target=self.target,
                target_fingerprint=self.fingerprint,
                request_id="scope-primary-one-exact",
                shared_build_request_id=f"grade-build:{self.fingerprint}",
                now=1_002,
            )
            excluded_before = {
                row["id"]: dict(row)
                for row in conn.execute(
                    """
                    SELECT * FROM learning_curriculum_preparation_plans
                    WHERE id IN (?, ?)
                    ORDER BY id
                    """,
                    (primary_two["id"], stale["id"]),
                ).fetchall()
            }
            excluded_event_counts_before = {
                plan_id: int(
                    conn.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM learning_curriculum_preparation_events
                        WHERE plan_id = ?
                        """,
                        (plan_id,),
                    ).fetchone()["count"]
                )
                for plan_id in excluded_before
            }
            before = self.repository.count_runner_scope(
                conn,
                now=1_003,
                supported_stages=("queued", "planning", "generating_content"),
                grade_code="primary_1",
                target_fingerprint=self.fingerprint,
            )
            claimed = self.repository.claim_next(
                conn,
                now=1_003,
                lease_ms=90_000,
                supported_stages=("queued", "planning", "generating_content"),
                stage_deadline_ms={"planning": 120_000},
                grade_code="primary_1",
                target_fingerprint=self.fingerprint,
            )
            after = self.repository.count_runner_scope(
                conn,
                now=1_003,
                supported_stages=("queued", "planning", "generating_content"),
                grade_code="primary_1",
                target_fingerprint=self.fingerprint,
            )
            excluded_after = {
                row["id"]: dict(row)
                for row in conn.execute(
                    """
                    SELECT * FROM learning_curriculum_preparation_plans
                    WHERE id IN (?, ?)
                    ORDER BY id
                    """,
                    (primary_two["id"], stale["id"]),
                ).fetchall()
            }
            excluded_event_counts_after = {
                plan_id: int(
                    conn.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM learning_curriculum_preparation_events
                        WHERE plan_id = ?
                        """,
                        (plan_id,),
                    ).fetchone()["count"]
                )
                for plan_id in excluded_after
            }

        self.assertEqual(before, {
            "claimablePlanCount": 1,
            "runningPlanCount": 0,
            "expiredLeaseCount": 0,
        })
        self.assertEqual(claimed["id"], exact["id"])
        self.assertNotEqual(claimed["id"], primary_two["id"])
        self.assertNotEqual(claimed["id"], stale["id"])
        self.assertEqual(excluded_after, excluded_before)
        self.assertEqual(excluded_event_counts_after, excluded_event_counts_before)
        for row in excluded_after.values():
            self.assertEqual(row["status"], "queued")
            self.assertEqual(row["stage"], "queued")
            for field in (
                "lease_token",
                "lease_expires_at",
                "heartbeat_at",
                "hard_deadline_at",
                "work_unit_kind",
            ):
                self.assertIsNone(row[field], (row["id"], field, row[field]))
        self.assertEqual(claimed["status"], "running")
        self.assertEqual(claimed["stage"], "planning")
        self.assertEqual(after, {
            "claimablePlanCount": 0,
            "runningPlanCount": 1,
            "expiredLeaseCount": 0,
        })

    def test_invalid_v2_retry_authority_is_failed_without_starving_next_plan(self):
        with self.repository.transaction() as conn:
            invalid, _ = self._reserve(
                conn,
                request_id="invalid-v2-retry-authority",
                now=2_100,
            )
            valid, _ = self.repository.reserve_plan(
                conn,
                family_id="fam_2",
                child_id="child_2",
                grade_code="primary_1",
                school_year_start_year=2026,
                grade_selection_revision=1,
                target=self.target,
                target_fingerprint=self.fingerprint,
                request_id="valid-after-invalid-v2-retry",
                shared_build_request_id=f"grade-build:{self.fingerprint}",
                now=2_101,
            )
            first_claim = self.repository.claim_next(
                conn,
                now=2_100,
                lease_ms=100,
            )
            self.assertEqual(first_claim["id"], invalid["id"])
            self.assertTrue(
                self.repository.defer_claim(
                    conn,
                    plan_id=str(invalid["id"]),
                    lease_token=str(first_claim["lease_token"]),
                    target_fingerprint=self.fingerprint,
                    expected_stage="planning",
                    next_run_at=2_101,
                    error_code="preparation_dependency_unavailable",
                    now=2_101,
                )
            )
            conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET retry_reason_code = 'not_the_fixed_dependency_code',
                  retry_message_safe = 'not the fixed public message'
                WHERE id = ?
                """,
                (invalid["id"],),
            )

            next_claim = self.repository.claim_next(
                conn,
                now=2_102,
                lease_ms=100,
            )
            failed = self.repository.get_plan(conn, str(invalid["id"]))

        self.assertIsNotNone(next_claim)
        self.assertEqual(next_claim["id"], valid["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["stage"], "completed")
        self.assertEqual(failed["error_code"], "preparation_validation_failed")

    def test_invalid_v2_target_is_failed_without_starving_next_plan(self):
        with self.repository.transaction() as conn:
            invalid, _ = self._reserve(
                conn,
                request_id="invalid-v2-target-authority",
                now=2_200,
            )
            valid, _ = self.repository.reserve_plan(
                conn,
                family_id="fam_2",
                child_id="child_2",
                grade_code="primary_1",
                school_year_start_year=2026,
                grade_selection_revision=1,
                target=self.target,
                target_fingerprint=self.fingerprint,
                request_id="valid-after-invalid-v2-target",
                shared_build_request_id=f"grade-build:{self.fingerprint}",
                now=2_201,
            )
            conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET target_fingerprint = ?,
                  target_spec_json = ?, subject_progress_json = ?
                WHERE id = ?
                """,
                (
                    "0" * 64,
                    json.dumps(
                        {"schemaVersion": "mira.learning.preparation-target.v2"},
                        separators=(",", ":"),
                    ),
                    "{}",
                    invalid["id"],
                ),
            )

            next_claim = self.repository.claim_next(
                conn,
                now=2_202,
                lease_ms=100,
            )
            failed = self.repository.get_plan(conn, str(invalid["id"]))

        self.assertIsNotNone(next_claim)
        self.assertEqual(next_claim["id"], valid["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["stage"], "completed")
        self.assertEqual(failed["error_code"], "preparation_validation_failed")

    def test_request_or_identity_replay_with_different_owner_is_a_conflict(self):
        with self.repository.transaction() as conn:
            self._reserve(conn)
        with self.assertRaises(LearningCurriculumPreparationConflict):
            with self.repository.transaction() as conn:
                self._reserve(conn, family_id="fam_2", child_id="child_2")

        with self.assertRaises(LearningCurriculumPreparationConflict):
            with self.repository.transaction() as conn:
                self._reserve(
                    conn,
                    request_id="another-request",
                    school_year_start_year=2027,
                )

    def test_two_children_share_build_request_not_plan(self):
        with self.repository.transaction() as conn:
            first_child_plan, _ = self._reserve(conn)
            second_target = build_preparation_target("primary_1")
            second_child_plan, _ = self.repository.reserve_plan(
                conn,
                family_id="fam_2",
                child_id="child_2",
                grade_code="primary_1",
                school_year_start_year=2026,
                grade_selection_revision=1,
                target=second_target,
                target_fingerprint=self.fingerprint,
                request_id="grade:child_2:1",
                shared_build_request_id=f"grade-build:{self.fingerprint}",
                now=1000,
            )

        self.assertNotEqual(first_child_plan["id"], second_child_plan["id"])
        self.assertEqual(
            first_child_plan["shared_build_request_id"],
            second_child_plan["shared_build_request_id"],
        )

    def test_all_primary_grades_persist_canonical_subject_totals(self):
        expected_by_grade = {
            1: {"chinese": 12, "math": 9, "english": 9},
            2: {"chinese": 9, "math": 9, "english": 9},
            3: {"chinese": 9, "math": 9, "english": 9},
            4: {"chinese": 9, "math": 9, "english": 9},
            5: {"chinese": 9, "math": 9, "english": 9},
            6: {"chinese": 9, "math": 9, "english": 9},
        }
        with self.repository.transaction() as conn:
            for grade, expected in expected_by_grade.items():
                family_id = f"fam_grade_{grade}"
                child_id = f"child_grade_{grade}"
                self._insert_family_child(conn, family_id, child_id)
                target = build_preparation_target(f"primary_{grade}")
                fingerprint = preparation_target_fingerprint(target)
                plan, created = self.repository.reserve_plan(
                    conn,
                    family_id=family_id,
                    child_id=child_id,
                    grade_code=f"primary_{grade}",
                    school_year_start_year=2026,
                    grade_selection_revision=1,
                    target=target,
                    target_fingerprint=fingerprint,
                    request_id=f"grade:{child_id}:1",
                    shared_build_request_id=f"grade-build:{fingerprint}",
                    now=1800 + grade,
                )
                progress = json.loads(plan["subject_progress_json"])
                self.assertTrue(created)
                self.assertEqual(
                    {
                        subject: progress[subject]["totalCourseCount"]
                        for subject in ("chinese", "math", "english")
                    },
                    expected,
                )
                self.assertEqual(plan["total_course_count"], sum(expected.values()))

    def test_mutated_grade_subject_totals_are_rejected_even_with_matching_fingerprint(self):
        mutations = (("primary_1", 13, 31), ("primary_2", 12, 30))
        for offset, (grade_code, chinese_total, overall_total) in enumerate(
            mutations
        ):
            target = copy.deepcopy(build_preparation_target(grade_code))
            target["subjectTargets"]["chinese"][
                "totalCourseCount"
            ] = chinese_total
            target["totalCourseCount"] = overall_total
            fingerprint = preparation_target_fingerprint(target)
            with self.subTest(grade_code=grade_code):
                with self.assertRaisesRegex(ValueError, "canonical"):
                    with self.repository.transaction() as conn:
                        self.repository.reserve_plan(
                            conn,
                            family_id="fam_1",
                            child_id="child_1",
                            grade_code=grade_code,
                            school_year_start_year=2026,
                            grade_selection_revision=10 + offset,
                            target=target,
                            target_fingerprint=fingerprint,
                            request_id=f"mutated-target-{grade_code}",
                            shared_build_request_id=f"grade-build:{fingerprint}",
                            now=1900 + offset,
                        )

    def test_retry_creates_one_successor_and_keeps_failed_row(self):
        failed = self._create_failed_plan(now=1900)
        with self.repository.transaction() as conn:
            successor_a, created_a = self.repository.create_retry_successor(
                conn,
                failed_plan_id=failed["id"],
                family_id="fam_1",
                request_id="retry-1",
                now=2000,
            )
            successor_b, created_b = self.repository.create_retry_successor(
                conn,
                failed_plan_id=failed["id"],
                family_id="fam_1",
                request_id="retry-1",
                now=2001,
            )
            source = self.repository.get_plan(conn, failed["id"])

        self.assertTrue(created_a)
        self.assertFalse(created_b)
        self.assertEqual(successor_a["id"], successor_b["id"])
        self.assertEqual(source["status"], "failed")
        self.assertEqual(successor_a["retry_ordinal"], 1)
        self.assertEqual(successor_a["retry_of_plan_id"], failed["id"])
        self.assertEqual(successor_a["next_run_at"], 2000)
        self.assertEqual(successor_a["last_progress_at"], 2000)
        self.assertIsNone(successor_a["hard_deadline_at"])
        self.assertIsNone(successor_a["error_code"])

        with self.assertRaises(ValueError):
            with self.repository.transaction() as conn:
                self.repository.create_retry_successor(
                    conn,
                    failed_plan_id=successor_a["id"],
                    family_id="fam_1",
                    request_id="retry-2",
                    now=2002,
                )

    def test_v2_retry_preserves_trusted_per_subject_content_counts(self):
        with self.repository.transaction() as conn:
            plan, _ = self._reserve(
                conn, request_id="retry-content-count-source", now=2_050
            )
            claimed = self.repository.claim_next(
                conn, now=2_050, lease_ms=100
            )
            subject_progress = json.loads(str(plan["subject_progress_json"]))
            self.assertTrue(
                self.repository.mark_failed(
                    conn,
                    plan_id=plan["id"],
                    lease_token=claimed["lease_token"],
                    expected_stage="planning",
                    error_code="provider_failed",
                    error_message="provider failed",
                    ready_course_count=0,
                    failed_course_count=0,
                    subject_progress=subject_progress,
                    now=2_051,
                )
            )
            subject_progress["chinese"]["contentCandidateCount"] = 3
            conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET content_candidate_count = 3,
                  content_canary_candidate_count = 3,
                  stage_progress_json = ?, subject_progress_json = ?
                WHERE id = ?
                """,
                (
                    json.dumps(
                        {
                            "candidateCount": 3,
                            "canaryCandidateCount": 3,
                            "canaryFailedCount": 0,
                            "canaryTargetCount": 3,
                            "failedCount": 0,
                            "targetCount": 30,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    json.dumps(
                        subject_progress,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    plan["id"],
                ),
            )
            successor, _ = self.repository.create_retry_successor(
                conn,
                failed_plan_id=plan["id"],
                family_id="fam_1",
                request_id="retry-content-count-successor",
                now=2_052,
            )

        successor_progress = json.loads(str(successor["subject_progress_json"]))
        self.assertEqual(successor["content_candidate_count"], 3)
        self.assertEqual(successor["progress_percent"], 8)
        self.assertEqual(
            json.loads(str(successor["stage_progress_json"]))["candidateCount"],
            3,
        )
        self.assertEqual(
            successor_progress["chinese"]["contentCandidateCount"], 3
        )
        self.assertEqual(
            sum(
                int(item["contentCandidateCount"])
                for item in successor_progress.values()
            ),
            3,
        )

    def test_claim_is_single_winner_and_lease_token_guards_late_writer(self):
        with self.repository.transaction() as conn:
            self._reserve(conn)
        barrier = Barrier(2)

        def claim_once(now: int):
            repository = LearningCurriculumPreparationRepository(
                Database(self.database_url)
            )
            with repository.transaction() as conn:
                barrier.wait(timeout=10)
                return repository.claim_next(conn, now=now, lease_ms=60_000)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(claim_once, (3000, 3001)))
        winners = [row for row in results if row is not None]
        self.assertEqual(len(winners), 1, results)
        claimed = winners[0]

        with self.repository.transaction() as conn:
            self.assertIsNone(
                self.repository.claim_next(conn, now=3002, lease_ms=60_000)
            )
            updated = self.repository.heartbeat(
                conn,
                plan_id=claimed["id"],
                lease_token="wrong-token",
                target_fingerprint=self.fingerprint,
                now=3002,
                lease_ms=60_000,
            )
        self.assertFalse(updated)

    def test_empty_supported_stage_allowlist_returns_without_invalid_sql(self):
        with self.repository.transaction() as conn:
            self._reserve(conn, request_id="empty-stage-plan", now=3050)
            claimed = self.repository.claim_next(
                conn,
                now=3050,
                lease_ms=60_000,
                supported_stages=(),
            )
        self.assertIsNone(claimed)

    def test_claim_uses_90_second_lease_and_immutable_120_second_planning_deadline(self):
        with self.repository.transaction() as conn:
            queued, _ = self._reserve(conn, now=3100)
            self.assertEqual(queued["status"], "queued")
            self.assertEqual(queued["stage"], "queued")
            self.assertEqual(queued["next_run_at"], 3100)
            self.assertIsNone(queued["lease_token"])
            self.assertIsNone(queued["hard_deadline_at"])
            claimed = self.repository.claim_next(
                conn,
                now=3100,
                lease_ms=90_000,
                stage_deadline_ms={"planning": 120_000},
            )

        self.assertEqual(claimed["status"], "running")
        self.assertEqual(claimed["stage"], "planning")
        self.assertEqual(claimed["next_run_at"], 3100)
        self.assertIsNotNone(claimed["lease_token"])
        self.assertEqual(claimed["lease_expires_at"], 93_100)
        self.assertEqual(claimed["hard_deadline_at"], 123_100)

        with self.repository.transaction() as conn:
            reclaimed = self.repository.claim_next(
                conn,
                now=93_101,
                lease_ms=90_000,
                stage_deadline_ms={"planning": 999_000},
            )
        self.assertEqual(reclaimed["id"], claimed["id"])
        self.assertNotEqual(reclaimed["lease_token"], claimed["lease_token"])
        self.assertEqual(reclaimed["next_run_at"], 3100)
        self.assertEqual(reclaimed["hard_deadline_at"], 123_100)

    def test_heartbeat_extends_only_lease_not_hard_deadline(self):
        with self.repository.transaction() as conn:
            self._reserve(conn, request_id="heartbeat-plan", now=3250)
            claimed = self.repository.claim_next(conn, now=3250, lease_ms=100)
            original_deadline = claimed["hard_deadline_at"]
            self.assertFalse(
                self.repository.heartbeat(
                    conn,
                    plan_id=claimed["id"],
                    lease_token=claimed["lease_token"],
                    target_fingerprint="0" * 64,
                    now=3299,
                    lease_ms=1000,
                )
            )
            self.assertTrue(
                self.repository.heartbeat(
                    conn,
                    plan_id=claimed["id"],
                    lease_token=claimed["lease_token"],
                    target_fingerprint=self.fingerprint,
                    now=3300,
                    lease_ms=1000,
                )
            )
            updated = self.repository.get_plan(conn, claimed["id"])

        self.assertEqual(updated["heartbeat_at"], 3300)
        self.assertEqual(updated["lease_expires_at"], 4300)
        self.assertEqual(updated["hard_deadline_at"], original_deadline)

    def test_defer_claim_preserves_deadline_and_reclaims_exact_resume_stage(self):
        with self.repository.transaction() as conn:
            plan, _ = self._reserve(conn, request_id="release-plan", now=3350)
            claimed = self.repository.claim_next(
                conn,
                now=3350,
                lease_ms=100,
                stage_deadline_ms={"planning": 120_000},
            )
            deadline = claimed["hard_deadline_at"]
            self.assertTrue(
                self.repository.defer_claim(
                    conn,
                    plan_id=plan["id"],
                    lease_token=claimed["lease_token"],
                    target_fingerprint=self.fingerprint,
                    expected_stage="planning",
                    next_run_at=3351,
                    error_code="preparation_dependency_unavailable",
                    now=3351,
                )
            )
            waiting = self.repository.get_plan(conn, plan["id"])
            claimed_again = self.repository.claim_next(
                conn,
                now=3351,
                lease_ms=100,
                stage_deadline_ms={"planning": 999_000},
            )

        self.assertEqual(waiting["status"], "queued")
        self.assertEqual(waiting["stage"], "retry_wait")
        self.assertEqual(waiting["resume_stage"], "planning")
        self.assertEqual(waiting["next_run_at"], 3351)
        self.assertIsNone(waiting["lease_token"])
        self.assertEqual(waiting["hard_deadline_at"], deadline)
        self.assertEqual(claimed_again["stage"], "planning")
        self.assertEqual(claimed_again["hard_deadline_at"], deadline)

    def test_retry_wait_reclaims_exact_resume_stage(self):
        with self.repository.transaction() as conn:
            plan, _ = self._reserve(
                conn,
                grade_code="primary_2",
                request_id="legacy-v1-retry-wait",
                now=3300,
            )
            target = json.loads(plan["target_spec_json"])
            self.assertEqual(target["schemaVersion"], TARGET_SCHEMA_V1)
            self.assertEqual(
                plan["target_fingerprint"],
                preparation_target_fingerprint(target),
            )
            claimed = self.repository.claim_next(conn, now=3300, lease_ms=100)
            self.assertTrue(
                self.repository.mark_retry_wait(
                    conn,
                    plan_id=claimed["id"],
                    lease_token=claimed["lease_token"],
                    expected_stage="planning",
                    next_run_at=3500,
                    now=3302,
                )
            )
            waiting = self.repository.get_plan(conn, claimed["id"])

        self.assertEqual(waiting["status"], "queued")
        self.assertEqual(waiting["stage"], "retry_wait")
        self.assertEqual(waiting["resume_stage"], "planning")
        self.assertIsNone(waiting["lease_token"])
        self.assertEqual(waiting["hard_deadline_at"], claimed["hard_deadline_at"])
        self.assertIsNone(
            self._claim_in_transaction(now=3499, lease_ms=100)
        )
        resumed = self._claim_in_transaction(now=3500, lease_ms=100)
        self.assertEqual(resumed["stage"], "planning")
        self.assertIsNone(resumed["resume_stage"])

    def test_atomic_stage_result_rolls_back_state_when_event_append_fails(self):
        with self.repository.transaction() as conn:
            plan, _ = self._reserve(conn, request_id="atomic-event", now=3400)
            claimed = self.repository.claim_next(conn, now=3400, lease_ms=90_000)

        with self.assertRaisesRegex(RuntimeError, "event insert failed"):
            with self.repository.transaction() as conn:
                with patch.object(
                    self.repository,
                    "append_event",
                    side_effect=RuntimeError("event insert failed"),
                ):
                    self.repository.apply_stage_result(
                        conn,
                        plan_id=plan["id"],
                        lease_token=claimed["lease_token"],
                        target_fingerprint=self.fingerprint,
                        expected_stage="planning",
                        next_status="running",
                        next_stage="planning",
                        ready_course_count=0,
                        failed_course_count=0,
                        subject_progress=self._subject_progress(0),
                        next_run_at=claimed["hard_deadline_at"],
                        hard_deadline_at=claimed["hard_deadline_at"],
                        catalog_build_id="catalog_build_atomic",
                        catalog_release_id="catalog_release_atomic",
                        now=3401,
                    )

        with self.repository.transaction() as conn:
            unchanged = self.repository.get_plan(conn, plan["id"])
            events = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_curriculum_preparation_events WHERE plan_id = ?",
                (plan["id"],),
            ).fetchone()
        self.assertIsNone(unchanged["catalog_build_id"])
        self.assertEqual(events["count"], 0)

    def test_defer_claim_rolls_back_state_when_event_append_fails(self):
        with self.repository.transaction() as conn:
            plan, _ = self._reserve(conn, request_id="atomic-defer", now=3420)
            claimed = self.repository.claim_next(conn, now=3420, lease_ms=90_000)

        with self.assertRaisesRegex(RuntimeError, "event insert failed"):
            with self.repository.transaction() as conn:
                with patch.object(
                    self.repository,
                    "append_event",
                    side_effect=RuntimeError("event insert failed"),
                ):
                    self.repository.defer_claim(
                        conn,
                        plan_id=plan["id"],
                        lease_token=claimed["lease_token"],
                        target_fingerprint=self.fingerprint,
                        expected_stage="planning",
                        next_run_at=3421,
                        error_code="preparation_dependency_unavailable",
                        now=3421,
                    )

        with self.repository.transaction() as conn:
            unchanged = self.repository.get_plan(conn, plan["id"])
            events = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_curriculum_preparation_events WHERE plan_id = ?",
                (plan["id"],),
            ).fetchone()
        self.assertEqual(unchanged["status"], "running")
        self.assertEqual(unchanged["stage"], "planning")
        self.assertEqual(unchanged["lease_token"], claimed["lease_token"])
        self.assertEqual(events["count"], 0)

    def test_fail_claim_rolls_back_and_malformed_progress_uses_factual_counts(self):
        with self.repository.transaction() as conn:
            plan, _ = self._reserve(conn, request_id="atomic-fail", now=3430)
            claimed = self.repository.claim_next(conn, now=3430, lease_ms=90_000)
            conn.execute(
                "UPDATE learning_curriculum_preparation_plans "
                "SET subject_progress_json = '[]' WHERE id = ?",
                (plan["id"],),
            )

        failure = {
            "plan_id": plan["id"],
            "lease_token": claimed["lease_token"],
            "target_fingerprint": self.fingerprint,
            "expected_stage": "planning",
            "error_code": "preparation_validation_failed",
            "error_message_safe": "部分课程未通过系统校验，请重新准备",
            "now": 3431,
        }
        with self.assertRaisesRegex(RuntimeError, "event insert failed"):
            with self.repository.transaction() as conn:
                with patch.object(
                    self.repository,
                    "append_event",
                    side_effect=RuntimeError("event insert failed"),
                ):
                    self.repository.fail_claim(conn, **failure)

        with self.repository.transaction() as conn:
            unchanged = self.repository.get_plan(conn, plan["id"])
        self.assertEqual(unchanged["status"], "running")
        self.assertEqual(unchanged["subject_progress_json"], "[]")

        with self.repository.transaction() as conn:
            self.assertTrue(self.repository.fail_claim(conn, **failure))
            failed = self.repository.get_plan(conn, plan["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["ready_course_count"], 0)
        self.assertEqual(failed["failed_course_count"], 0)
        self.assertEqual(
            list(json.loads(failed["subject_progress_json"])),
            ["chinese", "math", "english"],
        )

    def test_v2_failure_rebuilds_malformed_subject_content_counts_for_retry(self):
        mutations = {
            "missing": lambda progress: progress["chinese"].pop(
                "contentFailedCount"
            ),
            "extra": lambda progress: progress["math"].update({"extra": 1}),
            "bool": lambda progress: progress["english"].update(
                {"contentCandidateCount": True}
            ),
            "global_mismatch": lambda progress: progress["chinese"].update(
                {"contentCandidateCount": 1, "contentFailedCount": 0}
            ),
        }
        for offset, (name, mutate) in enumerate(mutations.items()):
            now = 3_440 + offset * 10
            with self.subTest(name=name):
                with self.repository.transaction() as conn:
                    plan, _ = self._reserve(
                        conn,
                        request_id=f"v2-malformed-failure-{name}",
                        revision=10 + offset,
                        now=now,
                    )
                    claimed = self.repository.claim_next(
                        conn, now=now, lease_ms=90_000
                    )
                    self.assertEqual(claimed["id"], plan["id"])
                    progress = json.loads(str(plan["subject_progress_json"]))
                    mutate(progress)
                    conn.execute(
                        """
                        UPDATE learning_curriculum_preparation_plans
                        SET content_candidate_count = 3,
                          content_failed_count = 2,
                          stage_progress_json = ?, subject_progress_json = ?
                        WHERE id = ?
                        """,
                        (
                            json.dumps(
                                {
                                    "candidateCount": 3,
                                    "canaryCandidateCount": 0,
                                    "canaryFailedCount": 0,
                                    "canaryTargetCount": 3,
                                    "failedCount": 2,
                                    "targetCount": 30,
                                },
                                separators=(",", ":"),
                            ),
                            json.dumps(
                                progress,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                            plan["id"],
                        ),
                    )
                    self.assertTrue(
                        self.repository.fail_claim(
                            conn,
                            plan_id=plan["id"],
                            lease_token=claimed["lease_token"],
                            target_fingerprint=plan["target_fingerprint"],
                            expected_stage="planning",
                            error_code="preparation_validation_failed",
                            error_message_safe=(
                                "部分课程未通过系统校验，请重新准备"
                            ),
                            now=now + 1,
                        )
                    )
                    failed = self.repository.get_plan(conn, plan["id"])
                    successor, _ = self.repository.create_retry_successor(
                        conn,
                        failed_plan_id=plan["id"],
                        family_id="fam_1",
                        request_id=f"v2-malformed-retry-{name}",
                        now=now + 2,
                    )
                    conn.execute(
                        "UPDATE learning_curriculum_preparation_plans "
                        "SET next_run_at = ? WHERE id = ?",
                        (now + 1_000_000, successor["id"]),
                    )

                failed_progress = json.loads(
                    str(failed["subject_progress_json"])
                )
                successor_progress = json.loads(
                    str(successor["subject_progress_json"])
                )
                self.assertEqual(
                    sum(
                        item["contentCandidateCount"]
                        for item in failed_progress.values()
                    ),
                    3,
                )
                self.assertEqual(
                    sum(
                        item["contentFailedCount"]
                        for item in failed_progress.values()
                    ),
                    2,
                )
                self.assertEqual(successor_progress, failed_progress)

    def test_stage_result_rejects_count_regression_and_build_replacement(self):
        with self.repository.transaction() as conn:
            plan, _ = self._reserve(conn, request_id="result-invariants", now=3440)
            claimed = self.repository.claim_next(conn, now=3440, lease_ms=90_000)
            common = {
                "plan_id": plan["id"],
                "lease_token": claimed["lease_token"],
                "target_fingerprint": self.fingerprint,
                "expected_stage": "planning",
                "next_status": "running",
                "next_stage": "planning",
                "failed_course_count": 0,
                "next_run_at": claimed["hard_deadline_at"],
                "hard_deadline_at": claimed["hard_deadline_at"],
                "catalog_release_id": "catalog_release_one",
                "now": 3441,
            }
            self.assertTrue(
                self.repository.apply_stage_result(
                    conn,
                    **common,
                    ready_course_count=2,
                    subject_progress=self._subject_progress(2),
                    catalog_build_id="catalog_build_one",
                )
            )
            with self.assertRaisesRegex(ValueError, "cannot decrease"):
                self.repository.apply_stage_result(
                    conn,
                    **common,
                    ready_course_count=1,
                    subject_progress=self._subject_progress(1),
                    catalog_build_id="catalog_build_one",
                )
            with self.assertRaisesRegex(ValueError, "cannot change"):
                self.repository.apply_stage_result(
                    conn,
                    **common,
                    ready_course_count=2,
                    subject_progress=self._subject_progress(2),
                    catalog_build_id="catalog_build_two",
                )

    def test_stage_result_cas_guards_token_fingerprint_and_writes_no_event(self):
        with self.repository.transaction() as conn:
            plan, _ = self._reserve(conn, request_id="stale-result", now=3450)
            claimed = self.repository.claim_next(conn, now=3450, lease_ms=100)
        with self.repository.transaction() as conn:
            newer_claim = self.repository.claim_next(
                conn,
                now=3551,
                lease_ms=90_000,
            )
        self.assertNotEqual(claimed["lease_token"], newer_claim["lease_token"])
        with self.repository.transaction() as conn:
            applied = self.repository.apply_stage_result(
                conn,
                plan_id=plan["id"],
                lease_token=claimed["lease_token"],
                target_fingerprint=self.fingerprint,
                expected_stage="planning",
                next_status="running",
                next_stage="planning",
                ready_course_count=0,
                failed_course_count=0,
                subject_progress=self._subject_progress(0),
                next_run_at=newer_claim["hard_deadline_at"],
                hard_deadline_at=newer_claim["hard_deadline_at"],
                catalog_build_id="catalog_build_stale",
                catalog_release_id="catalog_release_stale",
                now=3552,
            )
            events = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_curriculum_preparation_events WHERE plan_id = ?",
                (plan["id"],),
            ).fetchone()
        self.assertFalse(applied)
        self.assertEqual(events["count"], 0)

    def test_current_prefers_current_revision_and_retry_successor(self):
        failed = self._create_failed_plan(now=3600, revision=3)
        with self.repository.transaction() as conn:
            retry_successor, _ = self.repository.create_retry_successor(
                conn,
                failed_plan_id=failed["id"],
                family_id="fam_1",
                request_id="retry-current",
                now=3601,
            )
            current = self.repository.get_current_for_child(
                conn,
                family_id="fam_1",
                child_id="child_1",
                grade_selection_revision=3,
                target_fingerprint=self.fingerprint,
            )
            family_plan = self.repository.get_plan_for_family(
                conn,
                family_id="fam_1",
                plan_id=retry_successor["id"],
            )
            other_family = self.repository.get_plan_for_family(
                conn,
                family_id="fam_2",
                plan_id=retry_successor["id"],
            )

        self.assertEqual(current["id"], retry_successor["id"])
        self.assertEqual(family_plan["id"], retry_successor["id"])
        self.assertIsNone(other_family)

    def test_current_and_other_supersession_methods_terminalize_exact_plans(self):
        with self.repository.transaction() as conn:
            current, _ = self._reserve(
                conn,
                request_id="supersede-current",
                revision=20,
                now=3700,
            )
            claimed = self.repository.claim_next(conn, now=3700, lease_ms=100)
            self.assertEqual(claimed["id"], current["id"])
            self.assertTrue(
                self.repository.supersede_current_nonterminal(
                    conn,
                    family_id="fam_1",
                    child_id="child_1",
                    grade_selection_revision=20,
                    target_fingerprint=self.fingerprint,
                    now=3701,
                )
            )
            superseded_current = self.repository.get_plan(conn, current["id"])

            older, _ = self._reserve(
                conn,
                request_id="supersede-older",
                revision=21,
                now=3702,
            )
            kept, _ = self._reserve(
                conn,
                request_id="supersede-kept",
                revision=22,
                now=3703,
            )
            superseded_count = self.repository.supersede_other_nonterminal(
                conn,
                family_id="fam_1",
                child_id="child_1",
                keep_plan_id=kept["id"],
                now=3704,
            )
            superseded_older = self.repository.get_plan(conn, older["id"])
            still_current = self.repository.get_plan(conn, kept["id"])

        self.assertEqual(superseded_current["status"], "superseded")
        self.assertEqual(superseded_current["stage"], "completed")
        for field in (
            "lease_token",
            "lease_expires_at",
            "heartbeat_at",
            "next_run_at",
            "hard_deadline_at",
            "resume_stage",
        ):
            self.assertIsNone(superseded_current[field], field)
        self.assertEqual(superseded_count, 1)
        self.assertEqual(superseded_older["status"], "superseded")
        self.assertEqual(still_current["status"], "queued")

    def test_full_fake_state_flow_is_monotonic_and_terminal_clears_runtime_fields(self):
        with self.repository.transaction() as conn:
            plan, _ = self._reserve(
                conn,
                grade_code="primary_2",
                request_id="legacy-v1-full-state-flow",
                now=4000,
            )
            target = json.loads(plan["target_spec_json"])
            self.assertEqual(target["schemaVersion"], TARGET_SCHEMA_V1)
            self.assertEqual(
                plan["target_fingerprint"],
                preparation_target_fingerprint(target),
            )
            claimed = self.repository.claim_next(conn, now=4000, lease_ms=60_000)
            current_stage = "planning"
            stages = [
                "generating_content",
                "building_classrooms",
                "generating_speech",
                "validating",
                "publishing",
            ]
            percentages = []
            for offset, stage in enumerate(stages, start=1):
                ready_count = min(offset * 4, 26)
                self.assertTrue(
                    self.repository.transition_stage(
                        conn,
                        plan_id=claimed["id"],
                        lease_token=claimed["lease_token"],
                        expected_stage=current_stage,
                        next_stage=stage,
                        ready_course_count=ready_count,
                        failed_course_count=0,
                        subject_progress=self._subject_progress(
                            ready_count, grade_code="primary_2"
                        ),
                        now=4000 + offset,
                        hard_deadline_at=60_000 + offset,
                    )
                )
                percentages.append(
                    self.repository.get_plan(conn, claimed["id"])[
                        "progress_percent"
                    ]
                )
                current_stage = stage
            self.assertEqual(percentages, sorted(percentages))
            self.assertTrue(
                self.repository.mark_ready(
                    conn,
                    plan_id=claimed["id"],
                    lease_token=claimed["lease_token"],
                    expected_stage="publishing",
                    ready_course_count=27,
                    subject_progress=self._subject_progress(
                        27, grade_code="primary_2"
                    ),
                    now=5000,
                )
            )
            completed = self.repository.get_plan(conn, claimed["id"])
            self.assertFalse(
                self.repository.transition_stage(
                    conn,
                    plan_id=claimed["id"],
                    lease_token=claimed["lease_token"],
                    expected_stage="completed",
                    next_stage="planning",
                    ready_course_count=27,
                    failed_course_count=0,
                    subject_progress=self._subject_progress(
                        27, grade_code="primary_2"
                    ),
                    now=5001,
                    hard_deadline_at=65_000,
                )
            )

        self.assertEqual(completed["status"], "ready")
        self.assertEqual(completed["stage"], "completed")
        self.assertEqual(completed["progress_percent"], 100)
        for field in (
            "lease_token",
            "lease_expires_at",
            "heartbeat_at",
            "next_run_at",
            "hard_deadline_at",
            "resume_stage",
        ):
            self.assertIsNone(completed[field], field)

    def test_subject_totals_are_validated_before_count_cas(self):
        with self.repository.transaction() as conn:
            self._reserve(conn, now=5100)
            claimed = self.repository.claim_next(conn, now=5100, lease_ms=100)
            invalid = self._subject_progress(4)
            invalid["math"]["readyCourseCount"] += 1
            with self.assertRaisesRegex(ValueError, "subject progress"):
                self.repository.transition_stage(
                    conn,
                    plan_id=claimed["id"],
                    lease_token=claimed["lease_token"],
                    expected_stage="planning",
                    next_stage="generating_content",
                    ready_course_count=4,
                    failed_course_count=0,
                    subject_progress=invalid,
                    now=5101,
                    hard_deadline_at=9000,
                )

    def test_bind_failure_sanitization_events_and_supersede_are_cas_guarded(self):
        with self.repository.transaction() as conn:
            plan, _ = self._reserve(conn, now=5200)
            claimed = self.repository.claim_next(conn, now=5200, lease_ms=100)
            self.assertFalse(
                self.repository.bind_shared_build(
                    conn,
                    plan_id=plan["id"],
                    lease_token="wrong",
                    catalog_build_id="build_1",
                    catalog_release_id="release_1",
                    now=5201,
                )
            )
            self.assertTrue(
                self.repository.bind_shared_build(
                    conn,
                    plan_id=plan["id"],
                    lease_token=claimed["lease_token"],
                    catalog_build_id="build_1",
                    catalog_release_id="release_1",
                    now=5201,
                )
            )
            event = self.repository.append_event(
                conn,
                plan_id=plan["id"],
                event_type="build_bound",
                stage="queued",
                payload={"catalogBuildId": "build_1", "readyCourseCount": 0},
                now=5202,
            )
            self.assertTrue(
                self.repository.mark_failed(
                    conn,
                    plan_id=plan["id"],
                    lease_token=claimed["lease_token"],
                    expected_stage="planning",
                    error_code="provider_failed",
                    error_message="api_key=very-secret-token",
                    ready_course_count=0,
                    failed_course_count=30,
                    subject_progress=self._subject_progress(0, failed=30),
                    now=5203,
                )
            )
            failed = self.repository.get_plan(conn, plan["id"])

        self.assertEqual(event["event_type"], "build_bound")
        self.assertNotIn("very-secret-token", failed["error_message_safe"])
        self.assertEqual(failed["stage"], "completed")
        self.assertEqual(failed["status"], "failed")
        self.assertIsNone(failed["next_run_at"])
        with self.assertRaises(ValueError):
            with self.repository.transaction() as conn:
                self.repository.append_event(
                    conn,
                    plan_id=plan["id"],
                    event_type="unsafe",
                    stage="completed",
                    payload={"message": "secret"},
                    now=5204,
                )

    def test_event_type_must_be_a_safe_bounded_code(self):
        with self.repository.transaction() as conn:
            plan, _ = self._reserve(conn, request_id="event-type-plan", now=5250)
            for event_type in (
                "provider secret=do-not-persist",
                "x" * 65,
                "../unsafe",
            ):
                with self.subTest(event_type=event_type):
                    with self.assertRaisesRegex(ValueError, "event type"):
                        self.repository.append_event(
                            conn,
                            plan_id=plan["id"],
                            event_type=event_type,
                            stage="queued",
                            payload={"readyCourseCount": 0},
                            now=5251,
                        )

    def test_checkpoint_schema_verifier_reports_exact_contract_after_two_replays(self):
        evidence = self._checkpoint_schema_evidence_after_two_replays()

        self.assertEqual(
            evidence,
            {
                "migrations": {
                    MIGRATION_VERSION: 1,
                    RUNNER_MIGRATION_VERSION: 1,
                    CONTENT_STAGE_MIGRATION_VERSION: 1,
                },
                "tables": [
                    "learning_curriculum_preparation_events",
                    "learning_curriculum_preparation_plans",
                ],
                "uniqueKeys": [
                    "uq_learning_prep_identity",
                    "uq_learning_prep_request",
                    "uq_learning_prep_retry_source",
                ],
                "foreignKeys": [
                    "fk_learning_prep_child",
                    "fk_learning_prep_event_plan",
                    "fk_learning_prep_family",
                    "fk_learning_prep_formal_history_exact",
                    "fk_learning_prep_retry",
                ],
                "checks": [
                    "chk_learning_prep_content_counts",
                    "chk_learning_prep_counts",
                    "chk_learning_prep_event_json",
                    "chk_learning_prep_formal_publication",
                    "chk_learning_prep_formal_state_evidence",
                    "chk_learning_prep_json",
                    "chk_learning_prep_lease_group",
                    "chk_learning_prep_retry",
                    "chk_learning_prep_retry_ordinal",
                    "chk_learning_prep_stage",
                    "chk_learning_prep_stage_progress_json",
                    "chk_learning_prep_status",
                ],
            },
        )

    def test_checkpoint_invalid_terminal_and_null_evidence_dml_returns_3819(self):
        error_codes = self._checkpoint_invalid_dml_error_codes()

        self.assertEqual(
            error_codes,
            {
                "failed_without_error_evidence": 3819,
                "ready_without_completed_evidence": 3819,
                "retry_wait_without_deadline": 3819,
                "running_without_deadline": 3819,
                "superseded_without_superseded_evidence": 3819,
            },
        )

    def test_show_create_has_unique_keys_and_evidence_checks_reject_invalid_dml(self):
        with self.database.transaction() as conn:
            create_row = conn.execute(
                "SHOW CREATE TABLE learning_curriculum_preparation_plans"
            ).fetchone()
        create_sql = next(
            value for key, value in create_row.items() if key != "Table"
        )
        for key_name in (
            "uq_learning_prep_identity",
            "uq_learning_prep_request",
            "uq_learning_prep_retry_source",
        ):
            self.assertIn(key_name, create_sql)

        with self.repository.transaction() as conn:
            plan, _ = self._reserve(conn, now=5300)
        invalid_updates = (
            "UPDATE learning_curriculum_preparation_plans "
            "SET lease_token = 'partial' WHERE id = ?",
            "UPDATE learning_curriculum_preparation_plans "
            "SET status = 'ready', stage = 'completed', next_run_at = NULL "
            "WHERE id = ?",
            "UPDATE learning_curriculum_preparation_plans "
            "SET retry_ordinal = 1 WHERE id = ?",
            "UPDATE learning_curriculum_preparation_plans "
            "SET subject_progress_json = 'not-json' WHERE id = ?",
            "UPDATE learning_curriculum_preparation_plans "
            "SET status = 'queued', stage = 'retry_wait', resume_stage = NULL "
            "WHERE id = ?",
            "UPDATE learning_curriculum_preparation_plans "
            "SET status = 'failed', stage = 'completed', completed_at = 1, "
            "next_run_at = NULL, error_code = NULL, error_message_safe = NULL "
            "WHERE id = ?",
        )
        for sql in invalid_updates:
            with self.assertRaises(pymysql.MySQLError, msg=sql):
                with self.database.transaction() as conn:
                    conn.execute(sql, (plan["id"],))

    def test_partial_migration_replay_creates_tables_and_constraints_once(self):
        with self.database.transaction() as conn:
            column = conn.execute(
                """
                SELECT COUNT(*) AS count FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'children'
                  AND COLUMN_NAME = 'grade_selection_revision'
                """
            ).fetchone()
            self.assertEqual(column["count"], 1)
            conn.execute("DROP TABLE learning_curriculum_preparation_events")
            conn.execute("DROP TABLE learning_curriculum_preparation_plans")
            conn.execute(
                "DELETE FROM schema_migrations WHERE version = ?",
                (MIGRATION_VERSION,),
            )

        run_migrations(self.database_url, verbose=False)
        run_migrations(self.database_url, verbose=False)
        with self.database.transaction() as conn:
            rows = conn.execute(
                """
                SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME IN (
                    'learning_curriculum_preparation_plans',
                    'learning_curriculum_preparation_events'
                  )
                """
            ).fetchall()
            migration_rows = conn.execute(
                "SELECT COUNT(*) AS count FROM schema_migrations WHERE version = ?",
                (MIGRATION_VERSION,),
            ).fetchone()
            check_rows = conn.execute(
                """
                SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'learning_curriculum_preparation_plans'
                  AND CONSTRAINT_TYPE = 'CHECK'
                """
            ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(migration_rows["count"], 1)
        self.assertGreaterEqual(len(check_rows), 8)

    def test_055_replay_accepts_deadline_preserving_retry_and_rejects_null_deadline(self):
        with self.repository.transaction() as conn:
            plan, _ = self._reserve(
                conn,
                grade_code="primary_2",
                request_id="migration-055-evidence",
                now=5350,
            )
            target = json.loads(plan["target_spec_json"])
            self.assertEqual(target["schemaVersion"], TARGET_SCHEMA_V1)
            self.assertEqual(
                plan["target_fingerprint"],
                preparation_target_fingerprint(target),
            )
            claimed = self.repository.claim_next(
                conn,
                now=5350,
                lease_ms=90_000,
                stage_deadline_ms={"planning": 120_000},
            )
            conn.execute(
                "DELETE FROM schema_migrations WHERE version = ?",
                (RUNNER_MIGRATION_VERSION,),
            )
            conn.execute(
                "DELETE FROM schema_migrations WHERE version = ?",
                (CONTENT_STAGE_MIGRATION_VERSION,),
            )
            conn.execute(
                "ALTER TABLE learning_curriculum_preparation_plans "
                "DROP CHECK chk_learning_prep_formal_state_evidence"
            )

        run_migrations(self.database_url, verbose=False)
        run_migrations(self.database_url, verbose=False)
        with self.database.transaction() as conn:
            migration_rows = conn.execute(
                """
                SELECT version, COUNT(*) AS count FROM schema_migrations
                WHERE version IN (?, ?) GROUP BY version
                """,
                (RUNNER_MIGRATION_VERSION, CONTENT_STAGE_MIGRATION_VERSION),
            ).fetchall()
            conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET status = 'queued', stage = 'retry_wait',
                  resume_stage = 'planning', lease_token = NULL,
                  lease_expires_at = NULL, heartbeat_at = NULL,
                  next_run_at = ?, hard_deadline_at = ?
                WHERE id = ?
                """,
                (5351, claimed["hard_deadline_at"], plan["id"]),
            )
        with self.assertRaises(pymysql.MySQLError):
            with self.database.transaction() as conn:
                conn.execute(
                    "UPDATE learning_curriculum_preparation_plans SET hard_deadline_at = NULL WHERE id = ?",
                    (plan["id"],),
                )
        self.assertEqual(
            {row["version"]: row["count"] for row in migration_rows},
            {
                RUNNER_MIGRATION_VERSION: 1,
                CONTENT_STAGE_MIGRATION_VERSION: 1,
            },
        )

    def test_055_upgrade_normalizes_054_legacy_rows_before_replacing_check(self):
        retry_id, running_queued_id = self._install_legacy_054_rows(
            install_old_check=True
        )

        run_migrations(self.database_url, verbose=False)
        run_migrations(self.database_url, verbose=False)

        self._assert_055_legacy_upgrade(retry_id, running_queued_id)

    def test_055_restart_after_partial_ddl_restores_check_for_legacy_rows(self):
        retry_id, running_queued_id = self._install_legacy_054_rows(
            install_old_check=False
        )

        run_migrations(self.database_url, verbose=False)
        run_migrations(self.database_url, verbose=False)

        self._assert_055_legacy_upgrade(retry_id, running_queued_id)

    def test_orphan_family_cleanup_cascades_plan_retry_and_events(self):
        failed = self._create_failed_plan(now=5400)
        with self.repository.transaction() as conn:
            retry, _ = self.repository.create_retry_successor(
                conn,
                failed_plan_id=failed["id"],
                family_id="fam_1",
                request_id="retry-cascade",
                now=5401,
            )
            self.repository.append_event(
                conn,
                plan_id=failed["id"],
                event_type="failed",
                stage="completed",
                payload={"errorCode": "provider_failed"},
                now=5402,
            )
            self.repository.append_event(
                conn,
                plan_id=retry["id"],
                event_type="retry_created",
                stage="queued",
                payload={"sourcePlanId": failed["id"], "retryOrdinal": 1},
                now=5403,
            )

        profile_repository = ProfileRepository(self.database)
        with profile_repository.transaction() as conn:
            profile_repository.cleanup_orphan_family(conn, family_id="fam_1")
            plans = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM learning_curriculum_preparation_plans
                WHERE family_id = ?
                """,
                ("fam_1",),
            ).fetchone()
            events = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM learning_curriculum_preparation_events
                WHERE plan_id IN (?, ?)
                """,
                (failed["id"], retry["id"]),
            ).fetchone()
            family = conn.execute(
                "SELECT id FROM families WHERE id = ?",
                ("fam_1",),
            ).fetchone()
        self.assertEqual(plans["count"], 0)
        self.assertEqual(events["count"], 0)
        self.assertIsNone(family)

    def _checkpoint_schema_evidence_after_two_replays(self):
        run_migrations(self.database_url, verbose=False)
        run_migrations(self.database_url, verbose=False)
        preparation_tables = (
            "learning_curriculum_preparation_plans",
            "learning_curriculum_preparation_events",
        )
        with self.database.transaction() as conn:
            migration_rows = conn.execute(
                """
                SELECT version, COUNT(*) AS count
                FROM schema_migrations
                WHERE version IN (?, ?, ?)
                GROUP BY version
                ORDER BY version
                """,
                (
                    MIGRATION_VERSION,
                    RUNNER_MIGRATION_VERSION,
                    CONTENT_STAGE_MIGRATION_VERSION,
                ),
            ).fetchall()
            table_rows = conn.execute(
                """
                SELECT TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME IN (?, ?)
                ORDER BY TABLE_NAME
                """,
                preparation_tables,
            ).fetchall()
            constraint_rows = conn.execute(
                """
                SELECT CONSTRAINT_NAME, CONSTRAINT_TYPE
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME IN (?, ?)
                  AND CONSTRAINT_TYPE IN ('UNIQUE', 'FOREIGN KEY', 'CHECK')
                ORDER BY CONSTRAINT_NAME
                """,
                preparation_tables,
            ).fetchall()

        by_type = {
            constraint_type: sorted(
                row["CONSTRAINT_NAME"]
                for row in constraint_rows
                if row["CONSTRAINT_TYPE"] == constraint_type
            )
            for constraint_type in ("UNIQUE", "FOREIGN KEY", "CHECK")
        }
        return {
            "migrations": {
                row["version"]: int(row["count"]) for row in migration_rows
            },
            "tables": [row["TABLE_NAME"] for row in table_rows],
            "uniqueKeys": by_type["UNIQUE"],
            "foreignKeys": by_type["FOREIGN KEY"],
            "checks": by_type["CHECK"],
        }

    def _checkpoint_invalid_dml_error_codes(self):
        with self.repository.transaction() as conn:
            plan, _ = self._reserve(
                conn,
                request_id="task-8-invalid-dml-evidence",
                now=5900,
            )

        invalid_updates = {
            "failed_without_error_evidence": (
                """
                UPDATE learning_curriculum_preparation_plans
                SET status = 'failed', stage = 'completed', completed_at = 5901,
                  next_run_at = NULL, error_code = NULL, error_message_safe = NULL
                WHERE id = ?
                """,
                (plan["id"],),
            ),
            "ready_without_completed_evidence": (
                """
                UPDATE learning_curriculum_preparation_plans
                SET status = 'ready', stage = 'completed', completed_at = NULL,
                  progress_percent = 100, ready_course_count = total_course_count,
                  failed_course_count = 0, next_run_at = NULL
                WHERE id = ?
                """,
                (plan["id"],),
            ),
            "retry_wait_without_deadline": (
                """
                UPDATE learning_curriculum_preparation_plans
                SET status = 'queued', stage = 'retry_wait',
                  resume_stage = 'planning', hard_deadline_at = NULL
                WHERE id = ?
                """,
                (plan["id"],),
            ),
            "running_without_deadline": (
                """
                UPDATE learning_curriculum_preparation_plans
                SET status = 'running', stage = 'planning',
                  lease_token = 'task-8-token', lease_expires_at = 6000,
                  heartbeat_at = 5901, hard_deadline_at = NULL
                WHERE id = ?
                """,
                (plan["id"],),
            ),
            "superseded_without_superseded_evidence": (
                """
                UPDATE learning_curriculum_preparation_plans
                SET status = 'superseded', stage = 'completed',
                  completed_at = 5901, superseded_at = NULL, next_run_at = NULL
                WHERE id = ?
                """,
                (plan["id"],),
            ),
        }
        error_codes = {}
        for label, (sql, params) in invalid_updates.items():
            try:
                with self.database.transaction() as conn:
                    conn.execute(sql, params)
            except pymysql.MySQLError as exc:
                error_codes[label] = int(exc.args[0])
            else:  # pragma: no cover - required failure evidence
                self.fail(f"invalid DML was accepted: {label}")
        return error_codes

    def _create_failed_plan(self, *, now: int, revision: int = 1):
        with self.repository.transaction() as conn:
            plan, _ = self._reserve(conn, now=now, revision=revision)
            claimed = self.repository.claim_next(conn, now=now, lease_ms=100)
            self.assertTrue(
                self.repository.mark_failed(
                    conn,
                    plan_id=plan["id"],
                    lease_token=claimed["lease_token"],
                    expected_stage="planning",
                    error_code="provider_failed",
                    error_message="provider failed",
                    ready_course_count=0,
                    failed_course_count=30,
                    subject_progress=self._subject_progress(0, failed=30),
                    now=now + 1,
                )
            )
            return self.repository.get_plan(conn, plan["id"])

    def _install_legacy_054_rows(self, *, install_old_check: bool):
        with self.repository.transaction() as conn:
            retry, _ = self._reserve(
                conn,
                grade_code="primary_2",
                request_id="legacy-retry-null-deadline",
                now=5500,
            )
            running, _ = self._reserve(
                conn,
                family_id="fam_2",
                child_id="child_2",
                grade_code="primary_3",
                request_id="legacy-running-queued",
                now=5501,
            )
            conn.execute(
                "ALTER TABLE learning_curriculum_preparation_plans "
                "DROP CHECK chk_learning_prep_formal_state_evidence"
            )
            conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET status = 'queued', stage = 'retry_wait',
                  resume_stage = 'planning', next_run_at = 5510,
                  hard_deadline_at = NULL
                WHERE id = ?
                """,
                (retry["id"],),
            )
            conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET status = 'running', stage = 'queued',
                  lease_token = 'legacy-token', lease_expires_at = 5600,
                  heartbeat_at = 5501, next_run_at = 5501,
                  hard_deadline_at = 5700
                WHERE id = ?
                """,
                (running["id"],),
            )
            if install_old_check:
                conn.execute(
                    """
                    ALTER TABLE learning_curriculum_preparation_plans
                    ADD CONSTRAINT chk_learning_prep_state_evidence CHECK (
                      (status = 'queued' AND stage = 'retry_wait'
                        AND next_run_at IS NOT NULL AND lease_token IS NULL
                        AND lease_expires_at IS NULL AND heartbeat_at IS NULL
                        AND hard_deadline_at IS NULL AND resume_stage IN (
                          'planning', 'generating_content', 'building_classrooms',
                          'generating_speech', 'validating', 'publishing'
                        ) AND completed_at IS NULL AND superseded_at IS NULL
                        AND error_code IS NULL AND error_message_safe IS NULL)
                      OR
                      (status = 'running' AND stage = 'queued'
                        AND next_run_at IS NOT NULL AND lease_token IS NOT NULL
                        AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL
                        AND hard_deadline_at IS NOT NULL AND resume_stage IS NULL
                        AND completed_at IS NULL AND superseded_at IS NULL
                        AND error_code IS NULL AND error_message_safe IS NULL)
                      OR
                      (status = 'failed' AND stage = 'completed'
                        AND completed_at IS NOT NULL AND superseded_at IS NULL
                        AND error_code IS NOT NULL AND error_message_safe IS NOT NULL
                        AND lease_token IS NULL AND lease_expires_at IS NULL
                        AND heartbeat_at IS NULL AND next_run_at IS NULL
                        AND hard_deadline_at IS NULL AND resume_stage IS NULL)
                    )
                    """
                )
            conn.execute(
                "DELETE FROM schema_migrations WHERE version = ?",
                (RUNNER_MIGRATION_VERSION,),
            )
            conn.execute(
                "DELETE FROM schema_migrations WHERE version = ?",
                (CONTENT_STAGE_MIGRATION_VERSION,),
            )
        return retry["id"], running["id"]

    def _assert_055_legacy_upgrade(self, retry_id: str, running_id: str):
        with self.repository.transaction() as conn:
            retry = self.repository.get_plan(conn, retry_id)
            running = self.repository.get_plan(conn, running_id)
            checks = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'learning_curriculum_preparation_plans'
                  AND CONSTRAINT_NAME = 'chk_learning_prep_content_state_evidence'
                  AND CONSTRAINT_TYPE = 'CHECK'
                """
            ).fetchone()
            old_checks = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'learning_curriculum_preparation_plans'
                  AND CONSTRAINT_NAME = 'chk_learning_prep_state_evidence'
                  AND CONSTRAINT_TYPE = 'CHECK'
                """
            ).fetchone()
            migration_rows = conn.execute(
                """
                SELECT version, COUNT(*) AS count FROM schema_migrations
                WHERE version IN (?, ?) GROUP BY version
                """,
                (RUNNER_MIGRATION_VERSION, CONTENT_STAGE_MIGRATION_VERSION),
            ).fetchall()
        self.assertEqual(checks["count"], 1)
        self.assertEqual(old_checks["count"], 0)
        self.assertEqual(
            {row["version"]: row["count"] for row in migration_rows},
            {
                RUNNER_MIGRATION_VERSION: 1,
                CONTENT_STAGE_MIGRATION_VERSION: 1,
            },
        )
        self.assertEqual(retry["status"], "failed")
        self.assertEqual(retry["stage"], "completed")
        self.assertEqual(
            retry["error_code"], "preparation_upgrade_retry_state_invalid"
        )
        self.assertEqual(
            retry["error_message_safe"],
            "课程准备重试状态已安全终止，请重新准备",
        )
        self.assertEqual(running["status"], "running")
        self.assertEqual(running["stage"], "planning")

    def _reserve(
        self,
        conn,
        *,
        family_id: str = "fam_1",
        child_id: str = "child_1",
        grade_code: str = "primary_1",
        request_id: str = "grade:child_1:1",
        revision: int = 1,
        school_year_start_year: int = 2026,
        now: int = 1000,
    ):
        target = (
            self.target
            if grade_code == "primary_1"
            else build_preparation_target(grade_code)
        )
        fingerprint = preparation_target_fingerprint(target)
        return self.repository.reserve_plan(
            conn,
            family_id=family_id,
            child_id=child_id,
            grade_code=grade_code,
            school_year_start_year=school_year_start_year,
            grade_selection_revision=revision,
            target=target,
            target_fingerprint=fingerprint,
            request_id=request_id,
            shared_build_request_id=f"grade-build:{fingerprint}",
            now=now,
        )

    def _claim_in_transaction(self, *, now: int, lease_ms: int):
        with self.repository.transaction() as conn:
            return self.repository.claim_next(conn, now=now, lease_ms=lease_ms)

    def _subject_progress(
        self,
        ready: int,
        *,
        failed: int = 0,
        grade_code: str = "primary_1",
    ):
        totals = (
            {"chinese": 12, "math": 9, "english": 9}
            if grade_code == "primary_1"
            else {"chinese": 9, "math": 9, "english": 9}
        )
        result = {}
        remaining_ready = ready
        remaining_failed = failed
        for subject, total in totals.items():
            ready_count = min(total, remaining_ready)
            remaining_ready -= ready_count
            failed_count = min(total - ready_count, remaining_failed)
            remaining_failed -= failed_count
            result[subject] = {
                "totalCourseCount": total,
                "readyCourseCount": ready_count,
                "failedCourseCount": failed_count,
            }
            if grade_code == "primary_1":
                result[subject].update(
                    {
                        "contentCandidateCount": 0,
                        "contentFailedCount": 0,
                    }
                )
        return result

    @staticmethod
    def _insert_family_child(conn, family_id: str, child_id: str):
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


if __name__ == "__main__":
    unittest.main()
