from __future__ import annotations

import hashlib
import json
import re
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Literal, Mapping, Sequence

from core.config import LEARNING_CURRICULUM_PREPARATION_MIN_LEASE_SECONDS
from core.database import Database, DatabaseConnection, DatabaseRow
from integrations.openmaic_formal_media import compatible_preparation_target
from integrations.openmaic_question_adapter import QUESTION_PHASE_IO
from repositories.dynamic_learning_course_repository import (
    DynamicLearningCourseRepository,
)
from repositories.learning_question_fingerprint_inventory import (
    historical_question_fingerprint_snapshots,
)
from services.learning_curriculum_preparation_contract import (
    PREPARATION_CONTRACT_VERSION,
    PREPARATION_SUBJECTS,
    TARGET_SCHEMA_V2,
    build_preparation_target,
    compatible_preparation_scope_sql,
    preparation_target_fingerprint,
)
from services.learning_provider_deadline_contract import (
    provider_attempt_deadline_is_valid,
)
from services.learning_catalog_release_service import (
    ContentDispatchGraphAuditSnapshot,
    ContentHostDependencyAuditSnapshot,
    ContentParentRetryAuditSnapshot,
    ContentProofAuditSnapshot,
    ContentProviderDependencyAuditSnapshot,
)


_CONTENT_PROVIDER_PHASES = frozenset(
    str(authority["phase"]) for authority in QUESTION_PHASE_IO
)


class LearningCurriculumPreparationConflict(ValueError):
    """A stable request or plan identity was reused for different work."""


@dataclass(frozen=True)
class ParentRetryAuthoritySnapshot:
    authority_class: Literal[
        "pre_provider_dependency", "host_only_dependency", "not_replayable"
    ]
    provider_dispatch_count: int
    open_or_ambiguous_dispatch_count: int
    failed_safe_dispatch_count: int
    provider_graph_complete: bool
    next_work_kind: Literal["host_gate"] | None
    build_error_code: str | None


@dataclass(frozen=True)
class SharedBuildReconciliationSnapshot:
    updated_count: int
    exact_owner_handoff: bool


class LearningCurriculumPreparationRepository:
    FORMAL_V2_PROVIDER_STAGE_DEADLINE_MS = (
        LEARNING_CURRICULUM_PREPARATION_MIN_LEASE_SECONDS * 1000
    )
    FORMAL_PUBLICATION_CONTRACT_VERSION = (
        "mira.learning.formal-publication.v1"
    )
    CANDIDATE_BINDING_CONTRACT_VERSION = (
        "mira.learning.candidate-runtime-binding.v1"
    )
    STAGE_FLOORS = {
        "queued": 0,
        "planning": 5,
        "generating_content": 10,
        "building_classrooms": 40,
        "generating_speech": 65,
        "validating": 85,
        "publishing": 95,
        "completed": 100,
    }
    WORK_STAGES = (
        "planning",
        "generating_content",
        "building_classrooms",
        "generating_speech",
        "validating",
        "publishing",
    )
    CLAIMABLE_STAGES = ("queued", *WORK_STAGES)
    STAGE_DEADLINE_MS = {
        "planning": 2 * 60 * 1000,
        "generating_content": 10 * 60 * 1000,
        "building_classrooms": 45 * 60 * 1000,
        "generating_speech": 30 * 60 * 1000,
        "validating": 10 * 60 * 1000,
        "publishing": 2 * 60 * 1000,
    }
    PUBLIC_FAILURES = {
        "preparation_dependency_unavailable": "课程服务暂时不可用，请稍后重试",
        "preparation_generation_failed": "课程准备暂时失败，请稍后重试",
        "preparation_catalog_conflict": "课程目录请求冲突，请重新准备",
        "preparation_stage_deadline_exceeded": "课程准备时间较长，请重新准备",
        "preparation_validation_failed": "部分课程未通过系统校验，请重新准备",
        "preparation_upgrade_retry_state_invalid": "课程准备重试状态已安全终止，请重新准备",
    }
    CANONICAL_SUBJECT_TOTALS = {
        "primary_1": {"chinese": 12, "math": 9, "english": 9},
        **{
            f"primary_{grade}": {"chinese": 9, "math": 9, "english": 9}
            for grade in range(2, 7)
        },
    }
    ALLOWED_TRANSITIONS = {
        "queued": "planning",
        "planning": "generating_content",
        "generating_content": "building_classrooms",
        "building_classrooms": "generating_speech",
        "generating_speech": "validating",
        "validating": "publishing",
    }

    @classmethod
    def _claim_stage_deadline_ms(
        cls,
        *,
        is_v2: bool,
        next_stage: str,
        deadlines: Mapping[str, int],
    ) -> int:
        if is_v2 and next_stage in {"planning", "generating_content"}:
            return cls.FORMAL_V2_PROVIDER_STAGE_DEADLINE_MS
        return int(deadlines[next_stage])
    _SAFE_EVENT_KEYS = {
        "stage",
        "fromStage",
        "toStage",
        "status",
        "errorCode",
        "code",
        "retryOrdinal",
        "progressPercent",
        "validationReadyCount",
    }
    _SAFE_ATOM = re.compile(r"^[A-Za-z0-9_.:@/+-]{1,255}$")
    _SAFE_EVENT_TYPE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")

    def __init__(
        self,
        database: Database,
        *,
        content_proof_auditor: Callable[..., ContentProofAuditSnapshot]
        | None = None,
        content_dispatch_graph_auditor: Callable[
            ..., ContentDispatchGraphAuditSnapshot
        ]
        | None = None,
        content_parent_retry_auditor: Callable[
            ..., ContentParentRetryAuditSnapshot
        ]
        | None = None,
        content_provider_dependency_auditor: Callable[
            ..., ContentProviderDependencyAuditSnapshot
        ]
        | None = None,
        content_host_dependency_auditor: Callable[
            ..., ContentHostDependencyAuditSnapshot
        ]
        | None = None,
    ):
        self.database = database
        self.content_proof_auditor = content_proof_auditor
        self.content_dispatch_graph_auditor = content_dispatch_graph_auditor
        self.content_parent_retry_auditor = content_parent_retry_auditor
        self.content_provider_dependency_auditor = (
            content_provider_dependency_auditor
        )
        self.content_host_dependency_auditor = content_host_dependency_auditor

    @contextmanager
    def transaction(self) -> Iterator[DatabaseConnection]:
        with self.database.transaction() as conn:
            yield conn

    def reserve_plan(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str | None,
        child_id: str | None,
        grade_code: str,
        school_year_start_year: int,
        grade_selection_revision: int,
        target: Mapping[str, Any],
        target_fingerprint: str,
        request_id: str,
        shared_build_request_id: str,
        now: int,
        library_owned: bool = False,
    ) -> tuple[DatabaseRow, bool]:
        if library_owned:
            if family_id is not None or child_id is not None or grade_selection_revision != 0:
                raise ValueError("library production cannot belong to a child")
        elif not family_id or not child_id:
            raise ValueError("child preparation requires its family and child")
        normalized_target = dict(target)
        canonical_target_json = self._encode_json(normalized_target, sort_keys=True)
        actual_fingerprint = preparation_target_fingerprint(normalized_target)
        if str(target_fingerprint) != actual_fingerprint:
            raise ValueError("preparation target fingerprint mismatch")
        if str(normalized_target.get("gradeCode")) != str(grade_code):
            raise ValueError("preparation target grade mismatch")
        if (
            str(normalized_target.get("preparationContractVersion"))
            != PREPARATION_CONTRACT_VERSION
        ):
            raise ValueError("unsupported preparation contract version")
        if int(grade_selection_revision) < 0:
            raise ValueError("grade selection revision must be non-negative")
        self._validate_identifier(request_id, "request_id")
        self._validate_identifier(shared_build_request_id, "shared_build_request_id")

        subject_progress = self._initial_subject_progress(normalized_target)
        total_course_count = int(normalized_target.get("totalCourseCount") or 0)
        canonical_totals = self.CANONICAL_SUBJECT_TOTALS.get(str(grade_code))
        actual_totals = {
            subject: item["totalCourseCount"]
            for subject, item in subject_progress.items()
        }
        if canonical_totals is None or actual_totals != canonical_totals:
            raise ValueError("preparation target does not use canonical grade totals")
        if sum(
            item["totalCourseCount"] for item in subject_progress.values()
        ) != total_course_count:
            raise ValueError("preparation target subject totals do not match")
        if total_course_count != sum(canonical_totals.values()):
            raise ValueError("preparation target does not use canonical grade total")
        content_progress = self._initial_content_progress(normalized_target)

        plan_id = self._stable_id("learning_prep", request_id)
        cursor = conn.execute(
            """
            INSERT INTO learning_curriculum_preparation_plans(
              id, family_id, child_id, grade_code, school_year_start_year,
              grade_selection_revision, curriculum_version,
              preparation_contract_version, target_spec_json,
              target_fingerprint, request_id, shared_build_request_id,
              status, stage, total_course_count, ready_course_count,
              failed_course_count, progress_percent, subject_progress_json,
              content_target_count, content_candidate_count,
              content_failed_count, content_canary_target_count,
              content_canary_candidate_count, content_canary_failed_count,
              stage_progress_json,
              retry_of_plan_id, retry_ordinal, resume_stage, lease_token,
              lease_expires_at, heartbeat_at, next_run_at, hard_deadline_at,
              error_code, error_message_safe, last_progress_at, started_at,
              completed_at, superseded_at, created_at, updated_at,
              library_target_fingerprint
            )
            VALUES (
              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
              'queued', 'queued', ?, 0, 0, 0, ?, ?, 0, 0, ?, 0, 0, ?,
              NULL, 0, NULL, NULL,
              NULL, NULL, ?, NULL, NULL, NULL, ?, NULL, NULL, NULL, ?, ?, ?
            )
            ON DUPLICATE KEY UPDATE id = id
            """,
            (
                plan_id,
                family_id,
                child_id,
                grade_code,
                int(school_year_start_year),
                int(grade_selection_revision),
                str(normalized_target["curriculumVersion"]),
                str(normalized_target["preparationContractVersion"]),
                canonical_target_json,
                target_fingerprint,
                request_id,
                shared_build_request_id,
                total_course_count,
                self._encode_json(subject_progress),
                content_progress["targetCount"],
                content_progress["canaryTargetCount"],
                self._encode_json(content_progress, sort_keys=True),
                int(now),
                int(now),
                int(now),
                int(now),
                target_fingerprint if library_owned else None,
            ),
        )
        row = self._find_reservation(
            conn,
            request_id=request_id,
            child_id=child_id,
            grade_selection_revision=int(grade_selection_revision),
            target_fingerprint=target_fingerprint,
        )
        if row is None:
            raise RuntimeError("learning curriculum preparation plan was not persisted")
        self._assert_identity(
            row,
            family_id=family_id,
            child_id=child_id,
            grade_selection_revision=int(grade_selection_revision),
            target_fingerprint=target_fingerprint,
            retry_of_plan_id=None,
            retry_ordinal=0,
        )
        immutable = {
            "library_target_fingerprint": target_fingerprint if library_owned else None,
            "grade_code": grade_code,
            "school_year_start_year": int(school_year_start_year),
            "curriculum_version": str(normalized_target["curriculumVersion"]),
            "preparation_contract_version": str(
                normalized_target["preparationContractVersion"]
            ),
            "target_spec_json": canonical_target_json,
            "shared_build_request_id": shared_build_request_id,
        }
        if any(row[key] != value for key, value in immutable.items()):
            raise LearningCurriculumPreparationConflict(
                "plan identity is already bound to different preparation work"
            )
        return row, cursor.rowcount == 1

    def adopt_active_formal_release(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        family_id: str,
        child_id: str,
        grade_selection_revision: int,
        target_fingerprint: str,
        now: int,
    ) -> DatabaseRow | None:
        """Attach an already-published formal grade release to a child plan.

        Formal curriculum is generated once per immutable grade target. A later
        child selecting the same grade must reuse the active release instead of
        reopening the shared content build (which is intentionally sealed after
        publication).
        """

        self._validate_identifier(plan_id, "plan_id")
        self._validate_identifier(family_id, "family_id")
        self._validate_identifier(child_id, "child_id")
        self._require_timestamp(now, "now")
        if int(grade_selection_revision) < 0:
            raise ValueError("grade selection revision must be non-negative")
        if re.fullmatch(r"[0-9a-f]{64}", str(target_fingerprint or "")) is None:
            raise ValueError("target_fingerprint must be canonical SHA-256")

        plan = self.get_plan(conn, plan_id, for_update=True)
        if plan is None:
            return None
        self._assert_identity(
            plan,
            family_id=family_id,
            child_id=child_id,
            grade_selection_revision=int(grade_selection_revision),
            target_fingerprint=target_fingerprint,
            retry_of_plan_id=plan.get("retry_of_plan_id"),
            retry_ordinal=int(plan.get("retry_ordinal") or 0),
        )
        if str(plan.get("status") or "") == "ready":
            return plan
        reusable_state = bool(
            plan.get("superseded_at") is None
            and plan.get("lease_token") is None
            and (
                (
                    str(plan.get("status") or "") == "queued"
                    and str(plan.get("stage") or "") == "queued"
                )
                or (
                    str(plan.get("status") or "") == "failed"
                    and str(plan.get("stage") or "") == "completed"
                )
            )
        )
        if not reusable_state:
            return plan

        canonical_target = build_preparation_target("primary_1")
        try:
            plan_target = json.loads(str(plan.get("target_spec_json") or ""))
        except (TypeError, ValueError, json.JSONDecodeError):
            return plan
        if not (
            str(plan.get("grade_code") or "") == "primary_1"
            and compatible_preparation_target(plan_target, canonical_target)
            and preparation_target_fingerprint(plan_target) == target_fingerprint
            and str(plan.get("shared_build_request_id") or "")
            == f"grade-build:{target_fingerprint}"
        ):
            return plan

        authority = conn.execute(
            """
            SELECT
              pointer.pointer_revision,
              pointer.contract_version AS pointer_contract_version,
              pointer.release_id AS pointer_release_id,
              pointer.history_id AS pointer_history_id,
              pointer.activated_at AS pointer_activated_at,
              history.grade_code AS history_grade_code,
              history.target_fingerprint AS history_target_fingerprint,
              history.contract_version AS history_contract_version,
              history.release_id AS history_release_id,
              history.activation_source,
              history.publication_request_id,
              history.publication_receipt_hash,
              history.activated_at AS history_activated_at,
              history.superseded_at AS history_superseded_at,
              release_row.status AS release_status,
              release_row.quality_status AS release_quality_status,
              release_row.required_boundary_count,
              release_row.ready_item_count AS release_ready_item_count,
              build.id AS build_id,
              build.request_id AS build_request_id,
              build.release_id AS build_release_id,
              build.curriculum_version AS build_curriculum_version,
              build.status AS build_status,
              build.target_spec_json AS build_target_spec_json,
              build.total_item_count AS build_total_item_count,
              build.execution_mode AS build_execution_mode,
              build.stage_ceiling AS build_stage_ceiling
            FROM learning_curriculum_grade_release_pointers AS pointer
            JOIN learning_curriculum_grade_release_history AS history
              ON history.id = pointer.history_id
            JOIN learning_catalog_releases AS release_row
              ON release_row.id = pointer.release_id
            JOIN learning_catalog_build_jobs AS build
              ON build.release_id = release_row.id
            WHERE pointer.grade_code = 'primary_1'
              AND pointer.target_fingerprint = ?
              AND pointer.contract_version = ?
              AND pointer.pointer_revision >= 1
            LIMIT 1 FOR UPDATE
            """,
            (target_fingerprint, self.FORMAL_PUBLICATION_CONTRACT_VERSION),
        ).fetchone()
        if authority is None:
            return plan
        try:
            build_target = json.loads(str(authority["build_target_spec_json"]))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return plan
        receipt_hash = str(authority.get("publication_receipt_hash") or "")
        release_id = str(authority.get("pointer_release_id") or "")
        history_id = str(authority.get("pointer_history_id") or "")
        build_id = str(authority.get("build_id") or "")
        activated_at = int(authority.get("pointer_activated_at") or 0)
        if not (
            str(authority.get("pointer_contract_version") or "")
            == self.FORMAL_PUBLICATION_CONTRACT_VERSION
            and str(authority.get("history_grade_code") or "") == "primary_1"
            and str(authority.get("history_target_fingerprint") or "")
            == target_fingerprint
            and str(authority.get("history_contract_version") or "")
            == self.FORMAL_PUBLICATION_CONTRACT_VERSION
            and str(authority.get("history_release_id") or "") == release_id
            and str(authority.get("activation_source") or "")
            == "formal_publication"
            and authority.get("history_superseded_at") is None
            and bool(str(authority.get("publication_request_id") or ""))
            and re.fullmatch(r"[0-9a-f]{64}", receipt_hash) is not None
            and int(authority.get("history_activated_at") or 0) == activated_at > 0
            and str(authority.get("release_status") or "") == "published"
            and str(authority.get("release_quality_status") or "") == "ready"
            and int(authority.get("required_boundary_count") or 0) == 10
            and int(authority.get("release_ready_item_count") or 0) == 30
            and str(authority.get("build_request_id") or "")
            == f"grade-build:{target_fingerprint}"
            and str(authority.get("build_release_id") or "") == release_id
            and str(authority.get("build_curriculum_version") or "")
            == str(canonical_target["curriculumVersion"])
            and str(authority.get("build_status") or "")
            in {"running", "completed"}
            and self._encode_json(build_target, sort_keys=True)
            == self._encode_json(plan_target, sort_keys=True)
            and preparation_target_fingerprint(build_target)
            == target_fingerprint
            and int(authority.get("build_total_item_count") or 0) == 30
            and str(authority.get("build_execution_mode") or "")
            == "content_only"
            and str(authority.get("build_stage_ceiling") or "")
            == "content_ready"
        ):
            return plan

        build_items = conn.execute(
            """
            SELECT COUNT(*) AS item_count,
              COALESCE(SUM(
                status = 'course_ready'
                AND content_phase = 'course_ready'
                AND content_gate_status = 'passed'
                AND course_id IS NOT NULL AND course_id <> ''
                AND course_version IS NOT NULL AND course_version <> ''
              ), 0) AS exact_count
            FROM learning_catalog_build_items
            WHERE build_job_id = ? AND release_id = ?
            """,
            (build_id, release_id),
        ).fetchone()
        release_items = conn.execute(
            """
            SELECT COUNT(*) AS item_count,
              COALESCE(SUM(
                grade_code = 'primary_1'
                AND status = 'published'
                AND quality_status = 'ready'
                AND retired_at IS NULL
              ), 0) AS exact_count
            FROM learning_catalog_release_items
            WHERE release_id = ?
            """,
            (release_id,),
        ).fetchone()
        if not (
            build_items is not None
            and int(build_items.get("item_count") or 0) == 30
            and int(build_items.get("exact_count") or 0) == 30
            and release_items is not None
            and int(release_items.get("item_count") or 0) == 30
            and int(release_items.get("exact_count") or 0) == 30
        ):
            return plan

        subject_progress: dict[str, dict[str, int]] = {}
        for subject in PREPARATION_SUBJECTS:
            total = int(canonical_target["subjectTargets"][subject]["totalCourseCount"])
            subject_progress[subject] = {
                "totalCourseCount": total,
                "readyCourseCount": total,
                "failedCourseCount": 0,
                "contentCandidateCount": total,
                "contentFailedCount": 0,
            }
        stage_progress = {
            "candidateCount": 30,
            "canaryCandidateCount": 3,
            "canaryFailedCount": 0,
            "canaryTargetCount": 3,
            "failedCount": 0,
            "targetCount": 30,
        }
        updated = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET status = 'ready', stage = 'completed',
              catalog_build_id = ?, catalog_release_id = ?,
              ready_course_count = total_course_count,
              failed_course_count = 0, progress_percent = 100,
              subject_progress_json = ?, content_target_count = 30,
              content_candidate_count = 30, content_failed_count = 0,
              content_canary_target_count = 3,
              content_canary_candidate_count = 3,
              content_canary_failed_count = 0,
              content_canary_passed_at = ?,
              content_generation_completed_at = ?, stage_progress_json = ?,
              classroom_ready_count = total_course_count,
              speech_ready_count = total_course_count,
              validation_ready_count = total_course_count,
              published_course_count = total_course_count,
              formal_contract_version = ?,
              formal_publication_history_id = ?,
              formal_publication_receipt_hash = ?, formal_ready_at = ?,
              started_at = COALESCE(started_at, ?), completed_at = ?,
              lease_token = NULL, lease_expires_at = NULL,
              heartbeat_at = NULL, next_run_at = NULL,
              hard_deadline_at = NULL, resume_stage = NULL,
              work_unit_kind = NULL, bound_catalog_item_id = NULL,
              bound_content_attempt_ordinal = NULL,
              bound_content_phase = NULL, retry_reason_code = NULL,
              retry_message_safe = NULL, error_code = NULL,
              error_message_safe = NULL, last_progress_at = ?, updated_at = ?
            WHERE id = ? AND family_id = ? AND child_id = ?
              AND grade_selection_revision = ? AND target_fingerprint = ?
              AND superseded_at IS NULL AND lease_token IS NULL
              AND ((status = 'queued' AND stage = 'queued')
                OR (status = 'failed' AND stage = 'completed'))
            """,
            (
                build_id,
                release_id,
                self._encode_json(subject_progress),
                activated_at,
                activated_at,
                self._encode_json(stage_progress, sort_keys=True),
                self.FORMAL_PUBLICATION_CONTRACT_VERSION,
                history_id,
                receipt_hash,
                int(now),
                int(now),
                int(now),
                int(now),
                int(now),
                plan_id,
                family_id,
                child_id,
                int(grade_selection_revision),
                target_fingerprint,
            ),
        )
        if updated.rowcount == 1:
            self.append_event(
                conn,
                plan_id=plan_id,
                event_type="formal_release_reused",
                stage="completed",
                payload={
                    "releaseId": release_id,
                    "historyId": history_id,
                    "status": "ready",
                    "progressPercent": 100,
                },
                now=int(now),
            )
        return self.get_plan(conn, plan_id, for_update=True)

    def get_plan(
        self,
        conn: DatabaseConnection,
        plan_id: str,
        *,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            "SELECT * FROM learning_curriculum_preparation_plans "
            "WHERE id = ? LIMIT 1" + lock,
            (plan_id,),
        ).fetchone()

    def get_current_for_child(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        grade_selection_revision: int,
        target_fingerprint: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM learning_curriculum_preparation_plans
            WHERE family_id = ? AND child_id = ?
              AND grade_selection_revision = ? AND target_fingerprint = ?
            ORDER BY retry_ordinal DESC, created_at DESC
            LIMIT 1
            """,
            (
                family_id,
                child_id,
                int(grade_selection_revision),
                target_fingerprint,
            ),
        ).fetchone()

    def get_plan_for_family(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        plan_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM learning_curriculum_preparation_plans
            WHERE id = ? AND family_id = ? LIMIT 1
            """,
            (plan_id, family_id),
        ).fetchone()

    def create_retry_successor(
        self,
        conn: DatabaseConnection,
        *,
        failed_plan_id: str,
        family_id: str,
        request_id: str,
        now: int,
    ) -> tuple[DatabaseRow, bool]:
        self._validate_identifier(request_id, "request_id")
        source = self.get_plan(conn, failed_plan_id, for_update=True)
        if source is None or str(source["family_id"]) != family_id:
            raise ValueError("failed preparation plan was not found")
        if str(source["status"]) != "failed" or int(source["retry_ordinal"]) != 0:
            raise ValueError("only an original failed plan can be retried")

        source_progress = json.loads(str(source["subject_progress_json"]))
        self._validate_progress_counts(
            source,
            ready_course_count=int(source["ready_course_count"]),
            failed_course_count=int(source["failed_course_count"]),
            subject_progress=source_progress,
            monotonic=False,
        )
        retry_progress: dict[str, dict[str, int]] = {}
        source_target = json.loads(str(source["target_spec_json"]))
        is_v2 = str(source_target.get("schemaVersion") or "") == TARGET_SCHEMA_V2
        for subject in PREPARATION_SUBJECTS:
            item = source_progress[subject]
            retry_progress[subject] = {
                "totalCourseCount": int(item["totalCourseCount"]),
                "readyCourseCount": int(item["readyCourseCount"]),
                "failedCourseCount": 0,
            }
            if is_v2:
                retry_progress[subject].update(
                    {
                        "contentCandidateCount": item[
                            "contentCandidateCount"
                        ],
                        "contentFailedCount": item["contentFailedCount"],
                    }
                )
        if is_v2 and (
            sum(
                item["contentCandidateCount"]
                for item in retry_progress.values()
            )
            != int(source["content_candidate_count"])
            or sum(
                item["contentFailedCount"]
                for item in retry_progress.values()
            )
            != int(source["content_failed_count"])
            or any(
                item["contentCandidateCount"] < 0
                or item["contentFailedCount"] < 0
                or item["contentCandidateCount"]
                + item["contentFailedCount"]
                > item["totalCourseCount"]
                for item in retry_progress.values()
            )
        ):
            raise ValueError("retry subject content counts are inconsistent")
        ready_count = sum(
            item["readyCourseCount"] for item in retry_progress.values()
        )
        retry_progress_percent = (
            5
            + (
                30
                * int(source["content_candidate_count"])
                // max(1, int(source["content_target_count"]))
            )
            if is_v2
            else 0
        )
        retry_id = self._stable_id("learning_prep_retry", request_id)
        cursor = conn.execute(
            """
            INSERT INTO learning_curriculum_preparation_plans(
              id, family_id, child_id, grade_code, school_year_start_year,
              grade_selection_revision, curriculum_version,
              preparation_contract_version, target_spec_json,
              target_fingerprint, request_id, shared_build_request_id,
              status, stage, catalog_build_id, catalog_release_id,
              total_course_count, ready_course_count, failed_course_count,
              progress_percent, subject_progress_json, retry_of_plan_id,
              content_target_count, content_candidate_count,
              content_failed_count, content_canary_target_count,
              content_canary_candidate_count, content_canary_failed_count,
              content_canary_passed_at, content_generation_completed_at,
              stage_progress_json,
              retry_ordinal, resume_stage, lease_token, lease_expires_at,
              heartbeat_at, next_run_at, hard_deadline_at, error_code,
              error_message_safe, last_progress_at, started_at, completed_at,
              superseded_at, created_at, updated_at
            )
            VALUES (
              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 'queued', ?, ?,
              ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1,
              NULL, NULL, NULL, NULL, ?, NULL, NULL,
              NULL, ?, NULL, NULL, NULL, ?, ?
            )
            ON DUPLICATE KEY UPDATE id = id
            """,
            (
                retry_id,
                source["family_id"],
                source["child_id"],
                source["grade_code"],
                int(source["school_year_start_year"]),
                int(source["grade_selection_revision"]),
                source["curriculum_version"],
                source["preparation_contract_version"],
                source["target_spec_json"],
                source["target_fingerprint"],
                request_id,
                source["shared_build_request_id"],
                source["catalog_build_id"],
                source["catalog_release_id"],
                int(source["total_course_count"]),
                ready_count,
                retry_progress_percent,
                self._encode_json(retry_progress),
                source["id"],
                int(source["content_target_count"]),
                int(source["content_candidate_count"]),
                int(source["content_failed_count"]),
                int(source["content_canary_target_count"]),
                int(source["content_canary_candidate_count"]),
                int(source["content_canary_failed_count"]),
                source["content_canary_passed_at"],
                source["content_generation_completed_at"],
                source["stage_progress_json"],
                int(now),
                int(now),
                int(now),
                int(now),
            ),
        )
        row = self._find_retry(
            conn,
            request_id=request_id,
            failed_plan_id=failed_plan_id,
        )
        if row is None:
            raise RuntimeError("learning curriculum retry plan was not persisted")
        self._assert_identity(
            row,
            family_id=family_id,
            child_id=str(source["child_id"]),
            grade_selection_revision=int(source["grade_selection_revision"]),
            target_fingerprint=str(source["target_fingerprint"]),
            retry_of_plan_id=failed_plan_id,
            retry_ordinal=1,
        )
        return row, cursor.rowcount == 1

    def supersede_current_nonterminal(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        now: int,
        grade_selection_revision: int | None = None,
        target_fingerprint: str | None = None,
    ) -> bool:
        clauses = [
            "family_id = ?",
            "child_id = ?",
            "status IN ('queued', 'running')",
        ]
        params: list[Any] = [family_id, child_id]
        if grade_selection_revision is not None:
            clauses.append("grade_selection_revision = ?")
            params.append(int(grade_selection_revision))
        if target_fingerprint is not None:
            clauses.append("target_fingerprint = ?")
            params.append(target_fingerprint)
        row = conn.execute(
            "SELECT id FROM learning_curriculum_preparation_plans WHERE "
            + " AND ".join(clauses)
            + " ORDER BY retry_ordinal DESC, created_at DESC LIMIT 1 FOR UPDATE",
            params,
        ).fetchone()
        if row is None:
            return False
        return self._supersede_plan(conn, plan_id=str(row["id"]), now=now)

    def supersede_other_nonterminal(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        keep_plan_id: str,
        now: int,
    ) -> int:
        rows = conn.execute(
            """
            SELECT id FROM learning_curriculum_preparation_plans
            WHERE family_id = ? AND child_id = ? AND id <> ?
              AND status IN ('queued', 'running')
            ORDER BY created_at, id
            FOR UPDATE
            """,
            (family_id, child_id, keep_plan_id),
        ).fetchall()
        return sum(
            1
            for row in rows
            if self._supersede_plan(conn, plan_id=str(row["id"]), now=now)
        )

    @classmethod
    def _runner_target_scope(
        cls, grade_code: str | None, target_fingerprint: str | None,
    ) -> tuple[str, tuple[object, ...]]:
        if (grade_code is None) != (target_fingerprint is None):
            raise ValueError("runner grade and target scope must be paired")
        if grade_code is None:
            return "", ()
        cls._validate_identifier(grade_code, "grade_code")
        if re.fullmatch(r"[0-9a-f]{64}", target_fingerprint) is None:
            raise ValueError("target_fingerprint is invalid")
        if grade_code != "primary_1":
            return " AND grade_code = ? AND target_fingerprint = ?", (grade_code, target_fingerprint)
        current = build_preparation_target(grade_code)
        if preparation_target_fingerprint(current) != target_fingerprint:
            # Explicit historical/recovery callers retain their exact scope.
            return " AND grade_code = ? AND target_fingerprint = ?", (grade_code, target_fingerprint)
        paired, params = compatible_preparation_scope_sql(
            current, target_column="target_spec_json", fingerprint_column="target_fingerprint",
            automatic_only=True,
        )
        return " AND grade_code = ? AND " + paired, (grade_code, *params)

    def renew_undispatched_content_budget(
        self,
        conn: DatabaseConnection,
        *,
        grade_code: str,
        target_fingerprint: str,
        now: int,
        required_budget_ms: int,
    ) -> bool:
        """Recover queue time only for a proved, never-dispatched next phase.

        The logical attempt's outer deadline and every Provider receipt remain
        immutable. A stopped worker must not consume the next phase's execution
        window while that phase has never made a Provider call.
        """
        from repositories.learning_catalog_repository import LearningCatalogRepository

        if required_budget_ms <= 0 or self.content_provider_dependency_auditor is None:
            return False
        scope_clause, scope_params = self._runner_target_scope(grade_code, target_fingerprint)
        hint = conn.execute(
            f"""
            SELECT * FROM learning_curriculum_preparation_plans
            WHERE 1=1 {scope_clause}
              AND status = 'queued' AND stage = 'retry_wait'
              AND resume_stage = 'generating_content'
              AND work_unit_kind = 'provider_phase'
              AND lease_token IS NULL AND lease_expires_at IS NULL
              AND superseded_at IS NULL AND hard_deadline_at < ?
            ORDER BY next_run_at, created_at, id LIMIT 1
            """,
            (*scope_params, int(now) + required_budget_ms + 1_000),
        ).fetchone()
        if hint is None:
            return False
        target_fingerprint = str(hint["target_fingerprint"])
        item_id = str(hint.get("bound_catalog_item_id") or "")
        attempt = int(hint.get("bound_content_attempt_ordinal") or 0)
        phase = str(hint.get("bound_content_phase") or "")
        if not item_id or attempt not in {1, 2} or phase not in _CONTENT_PROVIDER_PHASES:
            return False
        sealed: list[object] = []
        authority = self._lock_shared_authority(
            conn,
            plan_id=str(hint["id"]),
            catalog_build_id=str(hint.get("catalog_build_id") or ""),
            catalog_item_id=item_id,
            provider_dependency_identity=(attempt, phase),
            reject_dispatch_identity=(attempt, phase),
            dependency_authority_out=sealed,
        )
        if authority is None or len(sealed) != 1:
            return False
        release, build, items, child, plan = authority
        item = items[0]
        old_deadline = int(item.get("content_work_unit_deadline_at") or 0)
        outer_deadline = int(item.get("content_provider_attempt_hard_deadline_at") or 0)
        new_deadline = LearningCatalogRepository._formal_content_work_deadline(
            now=now, outer_deadline=outer_deadline
        )
        if not (
            self._shared_authority_matches(
                release=release, build=build, items=None, child=child,
                plan=plan, target_fingerprint=target_fingerprint,
            )
            and isinstance(sealed[0], ContentProviderDependencyAuditSnapshot)
            and plan.get("status") == "queued" and plan.get("stage") == "retry_wait"
            and plan.get("resume_stage") == "generating_content"
            and plan.get("retry_reason_code") == "preparation_dependency_unavailable"
            and plan.get("work_unit_kind") == "provider_phase"
            and plan.get("bound_catalog_item_id") == item_id
            and plan.get("bound_content_attempt_ordinal") == attempt
            and plan.get("bound_content_phase") == phase
            and plan.get("hard_deadline_at") == old_deadline
            and plan.get("lease_token") is None and plan.get("lease_expires_at") is None
            and item.get("content_lease_token") is None
            and item.get("content_lease_expires_at") is None
            and new_deadline > old_deadline
            and new_deadline - int(now) >= required_budget_ms + 1_000
        ):
            return False
        updated = conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET content_work_unit_deadline_at = ?, updated_at = ?
            WHERE id = ? AND status = 'processing' AND content_phase = ?
              AND attempt_count = ? AND content_lease_token IS NULL
              AND content_work_unit_deadline_at = ?
              AND content_provider_attempt_hard_deadline_at = ?
            """,
            (new_deadline, int(now), item_id, phase, attempt, old_deadline, outer_deadline),
        )
        if updated.rowcount != 1:
            return False
        conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET hard_deadline_at = ?, next_run_at = ?, updated_at = ?
            WHERE catalog_build_id = ? AND target_fingerprint = ?
              AND bound_catalog_item_id = ? AND bound_content_attempt_ordinal = ?
              AND bound_content_phase = ? AND hard_deadline_at = ?
              AND status = 'queued' AND stage = 'retry_wait'
              AND work_unit_kind = 'provider_phase'
              AND lease_token IS NULL AND lease_expires_at IS NULL
            """,
            (new_deadline, int(now), int(now), str(build["id"]), target_fingerprint,
             item_id, attempt, phase, old_deadline),
        )
        self.append_event(
            conn, plan_id=str(plan["id"]), event_type="undispatched_budget_renewed",
            stage="retry_wait", payload={}, now=int(now),
        )
        return True

    def renew_saved_classroom_publication_lease(
        self, conn: DatabaseConnection, *, plan_id: str, lease_token: str,
        runtime_id: str, upstream_job_id: str, target_fingerprint: str,
        now: int, lease_ms: int,
    ) -> DatabaseRow | None:
        """Operator-only time for publishing an already verified saved classroom.

        This cannot renew a content/Provider phase or authorize generation. The
        running owner and exact ready Runtime must still have the claimed token;
        ordinary expired generation deadlines remain unchanged.
        """
        if not 0 < lease_ms <= 600_000:
            raise ValueError('saved publication lease must be at most ten minutes')
        row = conn.execute("""SELECT plan.*
            FROM learning_curriculum_preparation_plans AS plan
            JOIN learning_openmaic_runtime_classrooms AS runtime
              ON runtime.candidate_target_fingerprint = plan.library_target_fingerprint
             AND runtime.candidate_release_id = plan.catalog_release_id
            JOIN learning_catalog_build_items AS item
              ON item.id = runtime.candidate_build_item_id AND item.build_job_id = plan.catalog_build_id
            JOIN learning_curriculum_classroom_item_receipts AS receipt
              ON receipt.build_item_id = item.id AND receipt.runtime_classroom_id = runtime.id
             AND receipt.target_fingerprint = plan.library_target_fingerprint
             AND receipt.classroom_status = 'passed' AND receipt.publication_status <> 'published'
            WHERE plan.id = ? AND plan.library_target_fingerprint = ?
              AND plan.family_id IS NULL AND plan.child_id IS NULL
              AND plan.status = 'running' AND plan.work_unit_kind = 'coordinator'
              AND plan.lease_token = ? AND plan.lease_expires_at <= ? AND plan.hard_deadline_at <= ?
              AND plan.bound_catalog_item_id IS NULL AND plan.bound_content_phase IS NULL
              AND plan.bound_content_attempt_ordinal IS NULL
              AND plan.superseded_at IS NULL AND plan.completed_at IS NULL
              AND runtime.id = ? AND runtime.upstream_job_id = ?
              AND runtime.status = 'ready' AND runtime.retired_at IS NULL
            LIMIT 1 FOR UPDATE""",
            (plan_id, target_fingerprint, lease_token, int(now), int(now), runtime_id, upstream_job_id),
        ).fetchone()
        if row is None:
            return None
        deadline = int(now) + lease_ms
        conn.execute('UPDATE learning_curriculum_preparation_plans SET hard_deadline_at = ?, '
            'lease_expires_at = ?, heartbeat_at = ?, next_run_at = ?, updated_at = ? '
            'WHERE id = ? AND lease_token = ?',
            (deadline, deadline, int(now), int(now), int(now), plan_id, lease_token))
        self.append_event(conn, plan_id=plan_id, event_type='saved_classroom_publication_resumed',
            stage=str(row['stage']), payload={'code': 'saved_classroom_publication_resumed'}, now=int(now))
        return self.get_plan(conn, plan_id)

    def claim_next(
        self,
        conn: DatabaseConnection,
        *,
        now: int,
        lease_ms: int,
        supported_stages: Sequence[str] | None = None,
        stage_deadline_ms: Mapping[str, int] | None = None,
        grade_code: str | None = None,
        target_fingerprint: str | None = None,
    ) -> DatabaseRow | None:
        stages = self._supported_stages(supported_stages)
        if not stages:
            return None
        work_stages = tuple(stage for stage in stages if stage != "queued")
        stage_markers = ", ".join("?" for _ in stages)
        resume_markers = ", ".join("?" for _ in work_stages)
        resume_clause = (
            f"OR (stage = 'retry_wait' AND resume_stage IN ({resume_markers}))"
            if work_stages
            else ""
        )
        scope_clause, scope_params = self._runner_target_scope(grade_code, target_fingerprint)
        row = conn.execute(
            f"""
            SELECT * FROM learning_curriculum_preparation_plans
            WHERE status IN ('queued', 'running')
              AND next_run_at <= ?
              AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
              AND (library_target_fingerprint IS NOT NULL OR NOT EXISTS (
                SELECT 1 FROM learning_curriculum_preparation_plans AS library_owner
                WHERE library_owner.library_target_fingerprint =
                  learning_curriculum_preparation_plans.target_fingerprint
              ))
              AND (stage IN ({stage_markers}) {resume_clause})
              {scope_clause}
            ORDER BY next_run_at, created_at, id
            LIMIT 1 FOR UPDATE SKIP LOCKED
            """,
            (int(now), int(now), *stages, *work_stages, *scope_params),
        ).fetchone()
        if row is None:
            return None

        persisted_stage = str(row["stage"])
        next_stage = (
            "planning"
            if persisted_stage == "queued"
            else (
                str(row["resume_stage"])
                if persisted_stage == "retry_wait"
                else persisted_stage
            )
        )
        if next_stage not in self.WORK_STAGES:
            raise ValueError("preparation claim resolved to an unsupported work stage")
        try:
            is_v2 = self._is_v2_plan(row)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            is_v2 = False

        def reject_invalid_v2_target() -> DatabaseRow | None:
            self._fail_invalid_v2_claim_locked(
                conn,
                plan=row,
                failure_stage=next_stage,
                now=int(now),
            )
            return self.claim_next(
                conn,
                now=now,
                lease_ms=lease_ms,
                supported_stages=supported_stages,
                stage_deadline_ms=stage_deadline_ms,
                grade_code=grade_code,
                target_fingerprint=target_fingerprint,
            )

        try:
            self._validate_plan_target(row)
        except (
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            LearningCurriculumPreparationConflict,
        ):
            if is_v2:
                return reject_invalid_v2_target()
            raise
        deadlines = dict(self.STAGE_DEADLINE_MS)
        if stage_deadline_ms is not None:
            deadlines.update({str(key): int(value) for key, value in stage_deadline_ms.items()})
        def reject_invalid_v2_claim() -> DatabaseRow | None:
            self._fail_invalid_v2_claim_locked(
                conn,
                plan=row,
                failure_stage=next_stage,
                now=int(now),
            )
            return self.claim_next(
                conn,
                now=now,
                lease_ms=lease_ms,
                supported_stages=supported_stages,
                stage_deadline_ms=stage_deadline_ms,
                grade_code=grade_code,
                target_fingerprint=target_fingerprint,
            )

        deadline_ms = self._claim_stage_deadline_ms(
            is_v2=is_v2,
            next_stage=next_stage,
            deadlines=deadlines,
        )
        if deadline_ms <= 0:
            raise ValueError("preparation stage deadline must be positive")
        token = uuid.uuid4().hex
        preserve_retry_binding = is_v2 and persisted_stage == "retry_wait"
        preserve_crash_authority = False
        if is_v2:
            common_unleased = bool(
                row.get("lease_token") is None
                and row.get("lease_expires_at") is None
                and row.get("heartbeat_at") is None
            )
            preserve_crash_authority = bool(
                persisted_stage != "retry_wait"
                and isinstance(row.get("lease_token"), str)
                and bool(row.get("lease_token"))
                and type(row.get("lease_expires_at")) is int
                and int(row["lease_expires_at"]) <= int(now)
                and type(row.get("heartbeat_at")) is int
            )
            preserve_existing_authority = bool(
                preserve_retry_binding or preserve_crash_authority
            )
            if preserve_retry_binding and not common_unleased:
                return reject_invalid_v2_claim()
            if not common_unleased and not preserve_crash_authority:
                return reject_invalid_v2_claim()
            if preserve_existing_authority:
                original_deadline = row.get("hard_deadline_at")
                original_kind = str(row.get("work_unit_kind") or "")
                original_item = row.get("bound_catalog_item_id")
                original_attempt = row.get("bound_content_attempt_ordinal")
                original_phase = row.get("bound_content_phase")
                if (
                    type(original_deadline) is not int
                    or original_kind
                    not in {"coordinator", "provider_phase", "host_gate"}
                    or (
                        original_kind == "coordinator"
                        and any(
                            value is not None
                            for value in (
                                original_item,
                                original_attempt,
                                original_phase,
                            )
                        )
                        or (
                            original_kind == "coordinator"
                            and next_stage not in self.WORK_STAGES
                        )
                    )
                    or (
                        original_kind != "coordinator"
                        and (
                            not isinstance(original_item, str)
                            or not original_item
                            or type(original_attempt) is not int
                            or original_attempt not in {1, 2}
                            or not isinstance(original_phase, str)
                            or not original_phase
                            or next_stage != "generating_content"
                        )
                    )
                ):
                    return reject_invalid_v2_claim()
                if original_kind != "coordinator":
                    try:
                        if self._work_unit_kind(str(original_phase)) != original_kind:
                            return reject_invalid_v2_claim()
                    except ValueError:
                        return reject_invalid_v2_claim()
                if preserve_retry_binding and not (
                    str(row.get("status") or "") == "queued"
                    and str(row.get("stage") or "") == "retry_wait"
                    and str(row.get("retry_reason_code") or "")
                    == "preparation_dependency_unavailable"
                    and str(row.get("retry_message_safe") or "")
                    == self.PUBLIC_FAILURES["preparation_dependency_unavailable"]
                ):
                    return reject_invalid_v2_claim()
                if preserve_crash_authority and not (
                    str(row.get("status") or "") == "running"
                    and str(row.get("stage") or "") in self.WORK_STAGES
                    and row.get("resume_stage") is None
                    and row.get("retry_reason_code") is None
                    and row.get("retry_message_safe") is None
                ):
                    return reject_invalid_v2_claim()
            elif any(
                row.get(field) is not None
                for field in (
                    "hard_deadline_at",
                    "resume_stage",
                    "work_unit_kind",
                    "bound_catalog_item_id",
                    "bound_content_attempt_ordinal",
                    "bound_content_phase",
                    "retry_reason_code",
                    "retry_message_safe",
                )
            ):
                return reject_invalid_v2_claim()
        preserve_existing_authority = bool(
            preserve_retry_binding or preserve_crash_authority
        )
        work_unit_kind = (
            row.get("work_unit_kind")
            if preserve_existing_authority
            else ("coordinator" if is_v2 else None)
        )
        bound_item_id = (
            row.get("bound_catalog_item_id")
            if preserve_existing_authority
            else None
        )
        bound_attempt = (
            row.get("bound_content_attempt_ordinal")
            if preserve_existing_authority
            else None
        )
        bound_phase = (
            row.get("bound_content_phase")
            if preserve_existing_authority
            else None
        )
        hard_deadline_at = (
            int(row["hard_deadline_at"])
            if preserve_existing_authority
            else int(now) + deadline_ms
        )
        lease_expires_at = min(
            int(now) + max(1, int(lease_ms)), hard_deadline_at
        )
        cursor = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET status = 'running', stage = ?, resume_stage = NULL,
              lease_token = ?, lease_expires_at = ?, heartbeat_at = ?,
              hard_deadline_at = ?,
              work_unit_kind = ?, bound_catalog_item_id = ?,
              bound_content_attempt_ordinal = ?, bound_content_phase = ?,
              retry_reason_code = NULL, retry_message_safe = NULL,
              started_at = COALESCE(started_at, ?), updated_at = ?
            WHERE id = ? AND status IN ('queued', 'running')
              AND target_fingerprint = ?
              AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
              AND lease_token <=> ? AND lease_expires_at <=> ?
              AND heartbeat_at <=> ?
              AND hard_deadline_at <=> ?
              AND work_unit_kind <=> ?
              AND bound_catalog_item_id <=> ?
              AND bound_content_attempt_ordinal <=> ?
              AND bound_content_phase <=> ?
            """,
            (
                next_stage,
                token,
                lease_expires_at,
                int(now),
                hard_deadline_at,
                work_unit_kind,
                bound_item_id,
                bound_attempt,
                bound_phase,
                int(now),
                int(now),
                row["id"],
                row["target_fingerprint"],
                int(now),
                row.get("lease_token"),
                row.get("lease_expires_at"),
                row.get("heartbeat_at"),
                row.get("hard_deadline_at"),
                row.get("work_unit_kind"),
                row.get("bound_catalog_item_id"),
                row.get("bound_content_attempt_ordinal"),
                row.get("bound_content_phase"),
            ),
        )
        if cursor.rowcount != 1:
            return None
        return self.get_plan(conn, str(row["id"]))

    def heartbeat(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        lease_token: str,
        target_fingerprint: str,
        now: int,
        lease_ms: int,
    ) -> bool:
        cursor = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET lease_expires_at = LEAST(?, hard_deadline_at),
              heartbeat_at = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND lease_token = ?
              AND target_fingerprint = ? AND lease_expires_at > ?
              AND hard_deadline_at > ?
            """,
            (
                int(now) + max(1, int(lease_ms)),
                int(now),
                int(now),
                plan_id,
                lease_token,
                target_fingerprint,
                int(now),
                int(now),
            ),
        )
        return cursor.rowcount == 1

    def complete_shared_build_planning(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        plan_lease_token: str,
        target_fingerprint: str,
        catalog_build_id: str,
        catalog_release_id: str,
        now: int,
        next_run_at: int,
    ) -> bool:
        self._require_timestamp(now, "now")
        self._require_timestamp(next_run_at, "next_run_at")
        authority = self._lock_shared_authority(
            conn,
            plan_id=plan_id,
            catalog_build_id=catalog_build_id,
            catalog_release_id=catalog_release_id,
            lock_all_items=True,
        )
        if authority is None:
            return False
        release, build, items, child, plan = authority
        if not self._shared_authority_matches(
            release=release,
            build=build,
            items=items,
            child=child,
            plan=plan,
            target_fingerprint=target_fingerprint,
            allow_unbound_plan_catalog_ids=True,
        ):
            return False
        if not (
            str(plan.get("status") or "") == "running"
            and str(plan.get("stage") or "") == "planning"
            and str(plan.get("lease_token") or "") == plan_lease_token
            and int(plan.get("lease_expires_at") or 0) > int(now)
            and int(plan.get("hard_deadline_at") or 0) > int(now)
            and str(plan.get("work_unit_kind") or "") == "coordinator"
        ):
            return False
        cursor = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET status = 'running', stage = 'generating_content',
              catalog_build_id = ?, catalog_release_id = ?,
              progress_percent = GREATEST(progress_percent, 5),
              lease_token = NULL, lease_expires_at = NULL,
              heartbeat_at = NULL, next_run_at = ?, hard_deadline_at = NULL,
              resume_stage = NULL, work_unit_kind = NULL,
              bound_catalog_item_id = NULL,
              bound_content_attempt_ordinal = NULL,
              bound_content_phase = NULL, retry_reason_code = NULL,
              retry_message_safe = NULL, last_progress_at = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND stage = 'planning'
              AND lease_token = ? AND target_fingerprint = ?
              AND lease_expires_at > ? AND hard_deadline_at > ?
            """,
            (
                catalog_build_id,
                catalog_release_id,
                int(next_run_at),
                int(now),
                int(now),
                plan_id,
                plan_lease_token,
                target_fingerprint,
                int(now),
                int(now),
            ),
        )
        return cursor.rowcount == 1

    def authorize_shared_build_planning(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        plan_lease_token: str,
        target_fingerprint: str,
        now: int,
    ) -> bool:
        self._validate_identifier(plan_id, "plan_id")
        self._validate_identifier(plan_lease_token, "plan_lease_token")
        self._require_timestamp(now, "now")
        if not isinstance(target_fingerprint, str) or re.fullmatch(
            r"[0-9a-f]{64}", target_fingerprint
        ) is None:
            raise ValueError("target_fingerprint must be canonical SHA-256")
        hint = self.get_plan(conn, plan_id)
        if hint is None:
            return False
        child = conn.execute(
            """
            SELECT * FROM children
            WHERE id = ? AND family_id = ? LIMIT 1 FOR UPDATE
            """,
            (hint["child_id"], hint["family_id"]),
        ).fetchone()
        plan = self.get_plan(conn, plan_id, for_update=True)
        if plan is None or not self._plan_owner_matches(plan, child):
            return False
        hint_identity = (
            "family_id",
            "child_id",
            "grade_code",
            "grade_selection_revision",
            "target_fingerprint",
            "shared_build_request_id",
        )
        return bool(
            all(plan.get(key) == hint.get(key) for key in hint_identity)
            and self._planning_authority_matches(
                child=child,
                plan=plan,
                plan_lease_token=plan_lease_token,
                target_fingerprint=target_fingerprint,
                now=now,
            )
        )

    @classmethod
    def _planning_authority_matches(
        cls,
        *,
        child: Mapping[str, object],
        plan: Mapping[str, object],
        plan_lease_token: str,
        target_fingerprint: str,
        now: int,
    ) -> bool:
        try:
            target = json.loads(str(plan["target_spec_json"]))
            expected_target = build_preparation_target("primary_1")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return False
        empty_fields = (
            "bound_catalog_item_id",
            "bound_content_attempt_ordinal",
            "bound_content_phase",
            "resume_stage",
            "retry_reason_code",
            "retry_message_safe",
        )
        build_id = plan.get("catalog_build_id")
        release_id = plan.get("catalog_release_id")
        paired_catalog_identity = bool(
            (build_id is None and release_id is None)
            or (
                isinstance(build_id, str)
                and bool(build_id)
                and isinstance(release_id, str)
                and bool(release_id)
            )
        )
        return bool(
            compatible_preparation_target(target, expected_target)
            and str(target.get("schemaVersion") or "") == TARGET_SCHEMA_V2
            and str(target.get("gradeCode") or "") == "primary_1"
            and preparation_target_fingerprint(target) == target_fingerprint
            and str(plan.get("target_fingerprint") or "")
            == target_fingerprint
            and str(plan.get("shared_build_request_id") or "")
            == f"grade-build:{target_fingerprint}"
            and str(plan.get("grade_code") or "") == "primary_1"
            and str(plan.get("curriculum_version") or "")
            == str(target.get("curriculumVersion") or "")
            and str(plan.get("preparation_contract_version") or "")
            == str(target.get("preparationContractVersion") or "")
            and cls._plan_owner_matches(plan, child)
            and str(plan.get("status") or "") == "running"
            and str(plan.get("stage") or "") == "planning"
            and plan.get("completed_at") is None
            and plan.get("superseded_at") is None
            and str(plan.get("lease_token") or "") == plan_lease_token
            and int(plan.get("lease_expires_at") or 0) > int(now)
            and int(plan.get("hard_deadline_at") or 0) > int(now)
            and str(plan.get("work_unit_kind") or "") == "coordinator"
            and paired_catalog_identity
            and all(plan.get(field) is None for field in empty_fields)
        )

    def bind_content_work_unit(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        plan_lease_token: str,
        target_fingerprint: str,
        catalog_build_id: str,
        catalog_item_id: str,
        content_lease_token: str,
        logical_attempt: int,
        content_phase: str,
        item_work_unit_deadline_at: int,
        now: int,
    ) -> Mapping[str, object] | None:
        self._validate_content_binding_inputs(
            plan_id=plan_id,
            plan_lease_token=plan_lease_token,
            target_fingerprint=target_fingerprint,
            catalog_build_id=catalog_build_id,
            catalog_item_id=catalog_item_id,
            content_lease_token=content_lease_token,
            logical_attempt=logical_attempt,
            content_phase=content_phase,
            item_work_unit_deadline_at=item_work_unit_deadline_at,
            now=now,
        )
        plan_hint = self.get_plan(conn, plan_id)
        kind = self._work_unit_kind(content_phase)
        recovery_candidate = bool(
            plan_hint is not None
            and kind == "provider_phase"
            and str(plan_hint.get("work_unit_kind") or "") == kind
            and any(
                (
                    str(plan_hint.get("bound_catalog_item_id") or "")
                    != catalog_item_id,
                    int(plan_hint.get("bound_content_attempt_ordinal") or 0)
                    != logical_attempt,
                    str(plan_hint.get("bound_content_phase") or "")
                    != content_phase,
                    int(plan_hint.get("hard_deadline_at") or 0)
                    != item_work_unit_deadline_at,
                )
            )
        )
        recovery_authority: list[object] = []
        authority = self._lock_shared_authority(
            conn,
            plan_id=plan_id,
            catalog_build_id=catalog_build_id,
            catalog_item_id=catalog_item_id,
            provider_dependency_identity=(
                (logical_attempt, content_phase) if recovery_candidate else None
            ),
            dependency_authority_out=(
                recovery_authority if recovery_candidate else None
            ),
        )
        if authority is None:
            return None
        release, build, items, child, plan = authority
        item = items[0]
        if not self._shared_authority_matches(
            release=release,
            build=build,
            items=None,
            child=child,
            plan=plan,
            target_fingerprint=target_fingerprint,
        ):
            return None
        if not (
            self._content_work_item_authority_matches(
                release=release,
                build=build,
                item=item,
                logical_attempt=logical_attempt,
                content_phase=content_phase,
                content_lease_token=content_lease_token,
                item_work_unit_deadline_at=item_work_unit_deadline_at,
                now=now,
            )
            and str(plan.get("status") or "") == "running"
            and str(plan.get("stage") or "") == "generating_content"
            and str(plan.get("lease_token") or "") == plan_lease_token
            and int(plan.get("lease_expires_at") or 0) > int(now)
            and int(plan.get("hard_deadline_at") or 0) > int(now)
            and str(item.get("status") or "") == "processing"
            and int(item.get("attempt_count") or 0) == logical_attempt
            and str(item.get("content_phase") or "") == content_phase
            and str(item.get("content_lease_token") or "")
            == content_lease_token
            and int(item.get("content_lease_expires_at") or 0)
            == item_work_unit_deadline_at
            and int(item.get("content_work_unit_deadline_at") or 0)
            == item_work_unit_deadline_at
            and item_work_unit_deadline_at > int(now)
        ):
            return None
        existing_kind = str(plan.get("work_unit_kind") or "")
        if existing_kind not in {"coordinator", kind}:
            return None
        binding_changed = bool(existing_kind == kind and any(
            (
                str(plan.get("bound_catalog_item_id") or "")
                != catalog_item_id,
                int(plan.get("bound_content_attempt_ordinal") or 0)
                != logical_attempt,
                str(plan.get("bound_content_phase") or "") != content_phase,
                int(plan.get("hard_deadline_at") or 0)
                != item_work_unit_deadline_at,
            )
        ))
        if binding_changed:
            sealed_recovery = (
                recovery_authority[0] if len(recovery_authority) == 1 else None
            )
            if not (
                recovery_candidate
                and isinstance(
                    sealed_recovery, ContentProviderDependencyAuditSnapshot
                )
                and str(plan.get("bound_catalog_item_id") or "")
                == catalog_item_id
                and int(plan.get("bound_content_attempt_ordinal") or 0)
                == logical_attempt
                and str(plan.get("bound_content_phase") or "")
                == str(sealed_recovery.predecessor_final_phase or "")
                and sealed_recovery.predecessor_final_phase_ordinal is not None
            ):
                return None
        cursor = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET work_unit_kind = ?, bound_catalog_item_id = ?,
              bound_content_attempt_ordinal = ?, bound_content_phase = ?,
              hard_deadline_at = ?, lease_expires_at = LEAST(lease_expires_at, ?),
              heartbeat_at = ?, retry_reason_code = NULL,
              retry_message_safe = NULL, updated_at = ?
            WHERE id = ? AND status = 'running'
              AND stage = 'generating_content' AND lease_token = ?
              AND target_fingerprint = ? AND lease_expires_at > ?
              AND hard_deadline_at > ?
              AND work_unit_kind IN ('coordinator', ?)
            """,
            (
                kind,
                catalog_item_id,
                logical_attempt,
                content_phase,
                item_work_unit_deadline_at,
                item_work_unit_deadline_at,
                int(now),
                int(now),
                plan_id,
                plan_lease_token,
                target_fingerprint,
                int(now),
                int(now),
                kind,
            ),
        )
        # A retry claim already restores the exact persisted binding and may
        # use the same millisecond for its claim and bind writes. MySQL then
        # reports zero changed rows even though the locked authority above is
        # byte-identical and still owned by this plan lease.
        if cursor.rowcount not in {0, 1}:
            return None
        bound = self.get_plan(conn, plan_id)
        return dict(bound) if bound is not None else None

    def heartbeat_bound_content_work_unit(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        plan_lease_token: str,
        target_fingerprint: str,
        catalog_build_id: str,
        catalog_item_id: str,
        content_lease_token: str,
        logical_attempt: int,
        content_phase: str,
        item_work_unit_deadline_at: int,
        now: int,
        plan_lease_ms: int,
    ) -> bool:
        self._validate_content_binding_inputs(
            plan_id=plan_id,
            plan_lease_token=plan_lease_token,
            target_fingerprint=target_fingerprint,
            catalog_build_id=catalog_build_id,
            catalog_item_id=catalog_item_id,
            content_lease_token=content_lease_token,
            logical_attempt=logical_attempt,
            content_phase=content_phase,
            item_work_unit_deadline_at=item_work_unit_deadline_at,
            now=now,
        )
        self._require_positive_int(plan_lease_ms, "plan_lease_ms")
        authority = self._lock_shared_authority(
            conn,
            plan_id=plan_id,
            catalog_build_id=catalog_build_id,
            catalog_item_id=catalog_item_id,
        )
        if authority is None:
            return False
        release, build, items, child, plan = authority
        item = items[0]
        kind = self._work_unit_kind(content_phase)
        if not self._shared_authority_matches(
            release=release,
            build=build,
            items=None,
            child=child,
            plan=plan,
            target_fingerprint=target_fingerprint,
        ) or not (
            self._content_work_item_authority_matches(
                release=release,
                build=build,
                item=item,
                logical_attempt=logical_attempt,
                content_phase=content_phase,
                content_lease_token=content_lease_token,
                item_work_unit_deadline_at=item_work_unit_deadline_at,
                now=now,
            )
            and str(plan.get("status") or "") == "running"
            and str(plan.get("stage") or "") == "generating_content"
            and str(plan.get("lease_token") or "") == plan_lease_token
            and str(plan.get("work_unit_kind") or "") == kind
            and str(plan.get("bound_catalog_item_id") or "") == catalog_item_id
            and int(plan.get("bound_content_attempt_ordinal") or 0)
            == logical_attempt
            and str(plan.get("bound_content_phase") or "") == content_phase
            and int(plan.get("hard_deadline_at") or 0)
            == item_work_unit_deadline_at
            and int(plan.get("lease_expires_at") or 0) > int(now)
            and str(item.get("status") or "") == "processing"
            and int(item.get("attempt_count") or 0) == logical_attempt
            and str(item.get("content_phase") or "") == content_phase
            and str(item.get("content_lease_token") or "")
            == content_lease_token
            and int(item.get("content_lease_expires_at") or 0)
            == item_work_unit_deadline_at
            and int(item.get("content_work_unit_deadline_at") or 0)
            == item_work_unit_deadline_at
            and item_work_unit_deadline_at > int(now)
        ):
            return False
        item_cursor = conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET content_lease_expires_at = ?, content_heartbeat_at = ?,
              updated_at = ?
            WHERE id = ? AND build_job_id = ? AND status = 'processing'
              AND attempt_count = ? AND content_phase = ?
              AND content_lease_token = ?
              AND content_work_unit_deadline_at = ?
              AND content_lease_expires_at = ?
              AND content_work_unit_deadline_at > ?
            """,
            (
                item_work_unit_deadline_at,
                int(now),
                int(now),
                catalog_item_id,
                catalog_build_id,
                logical_attempt,
                content_phase,
                content_lease_token,
                item_work_unit_deadline_at,
                item_work_unit_deadline_at,
                int(now),
            ),
        )
        if item_cursor.rowcount not in {0, 1}:
            return False
        if item_cursor.rowcount == 0 and int(
            item.get("content_heartbeat_at") or 0
        ) != int(now):
            return False
        plan_cursor = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET lease_expires_at = LEAST(?, hard_deadline_at),
              heartbeat_at = ?, updated_at = ?
            WHERE id = ? AND status = 'running'
              AND stage = 'generating_content' AND lease_token = ?
              AND target_fingerprint = ? AND work_unit_kind = ?
              AND bound_catalog_item_id = ?
              AND bound_content_attempt_ordinal = ?
              AND bound_content_phase = ? AND hard_deadline_at = ?
              AND lease_expires_at > ? AND hard_deadline_at > ?
            """,
            (
                int(now) + plan_lease_ms,
                int(now),
                int(now),
                plan_id,
                plan_lease_token,
                target_fingerprint,
                kind,
                catalog_item_id,
                logical_attempt,
                content_phase,
                item_work_unit_deadline_at,
                int(now),
                int(now),
            ),
        )
        if plan_cursor.rowcount == 1:
            return True
        expected_plan_expiry = min(
            int(now) + plan_lease_ms,
            item_work_unit_deadline_at,
        )
        return bool(
            plan_cursor.rowcount == 0
            and int(plan.get("heartbeat_at") or 0) == int(now)
            and int(plan.get("lease_expires_at") or 0)
            == expected_plan_expiry
        )

    def authorize_content_control_work(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        plan_lease_token: str,
        target_fingerprint: str,
        catalog_build_id: str,
        now: int,
    ) -> bool:
        authority = self._lock_shared_authority(
            conn,
            plan_id=plan_id,
            catalog_build_id=catalog_build_id,
        )
        if authority is None:
            return False
        release, build, _items, child, plan = authority
        return bool(
            self._shared_authority_matches(
                release=release,
                build=build,
                items=None,
                child=child,
                plan=plan,
                target_fingerprint=target_fingerprint,
            )
            and self._active_content_build_matches(
                build, require_running=True
            )
            and str(plan.get("status") or "") == "running"
            and str(plan.get("stage") or "") == "generating_content"
            and str(plan.get("lease_token") or "") == plan_lease_token
            and str(plan.get("work_unit_kind") or "") == "coordinator"
            and plan.get("bound_catalog_item_id") is None
            and int(plan.get("lease_expires_at") or 0) > int(now)
            and int(plan.get("hard_deadline_at") or 0) > int(now)
        )

    def release_content_continuation(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        plan_lease_token: str,
        target_fingerprint: str,
        catalog_build_id: str,
        next_run_at: int,
        now: int,
        progressed: bool = True,
    ) -> bool:
        candidate = self.get_plan(conn, plan_id)
        item_id = (
            str(candidate.get("bound_catalog_item_id") or "")
            if candidate is not None
            else ""
        )
        authority = self._lock_shared_authority(
            conn,
            plan_id=plan_id,
            catalog_build_id=catalog_build_id,
            catalog_item_id=item_id or None,
        )
        if authority is None:
            return False
        release, build, _items, child, plan = authority
        if not self._shared_authority_matches(
            release=release,
            build=build,
            items=None,
            child=child,
            plan=plan,
            target_fingerprint=target_fingerprint,
        ) or not (
            self._active_content_build_matches(build, require_running=True)
            and str(plan.get("status") or "") == "running"
            and str(plan.get("stage") or "") == "generating_content"
            and str(plan.get("lease_token") or "") == plan_lease_token
            and int(plan.get("lease_expires_at") or 0) > int(now)
            and int(plan.get("hard_deadline_at") or 0) > int(now)
        ):
            return False
        cursor = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET status = 'running', stage = 'generating_content',
              lease_token = NULL, lease_expires_at = NULL,
              heartbeat_at = NULL, next_run_at = ?, hard_deadline_at = NULL,
              resume_stage = NULL, work_unit_kind = NULL,
              bound_catalog_item_id = NULL,
              bound_content_attempt_ordinal = NULL,
              bound_content_phase = NULL, retry_reason_code = NULL,
              retry_message_safe = NULL,
              last_progress_at = CASE WHEN ? THEN ? ELSE last_progress_at END,
              updated_at = ?
            WHERE id = ? AND status = 'running'
              AND stage = 'generating_content' AND lease_token = ?
              AND target_fingerprint = ?
              AND lease_expires_at > ? AND hard_deadline_at > ?
            """,
            (
                int(next_run_at),
                bool(progressed),
                int(now),
                int(now),
                plan_id,
                plan_lease_token,
                target_fingerprint,
                int(now),
                int(now),
            ),
        )
        return cursor.rowcount == 1

    def defer_bound_dependency(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        plan_lease_token: str,
        target_fingerprint: str,
        expected_stage: str,
        next_run_at: int,
        now: int,
        catalog_build_id: str,
        catalog_release_id: str,
        work_unit_kind: str,
        bound_catalog_item_id: str | None,
        bound_content_lease_token: str | None = None,
        bound_item_work_unit_deadline_at: int | None = None,
        bound_logical_attempt: int | None = None,
        bound_content_phase: str | None = None,
    ) -> bool:
        self._validate_identifier(catalog_build_id, "catalog_build_id")
        self._validate_identifier(catalog_release_id, "catalog_release_id")
        if bound_catalog_item_id is not None:
            self._validate_identifier(
                bound_catalog_item_id,
                "bound_catalog_item_id",
            )
        if work_unit_kind not in {"coordinator", "provider_phase", "host_gate"}:
            return False
        release_mutex = conn.execute(
            "SELECT * FROM learning_catalog_releases "
            "WHERE id = ? LIMIT 1 FOR UPDATE",
            (catalog_release_id,),
        ).fetchone()
        build_mutex = conn.execute(
            "SELECT * FROM learning_catalog_build_jobs "
            "WHERE id = ? AND release_id = ? LIMIT 1 FOR UPDATE",
            (catalog_build_id, catalog_release_id),
        ).fetchone()
        if release_mutex is None or build_mutex is None:
            return False
        hint = self.get_plan(conn, plan_id)
        if hint is None:
            return False
        if not (
            str(hint.get("catalog_build_id") or "") == catalog_build_id
            and str(hint.get("catalog_release_id") or "")
            == catalog_release_id
            and str(hint.get("work_unit_kind") or "") == work_unit_kind
            and hint.get("bound_catalog_item_id") == bound_catalog_item_id
        ):
            return False
        work_kind = work_unit_kind
        supplied_binding = (
            bound_content_lease_token,
            bound_item_work_unit_deadline_at,
            bound_logical_attempt,
            bound_content_phase,
        )
        if work_kind == "coordinator":
            if bound_catalog_item_id is not None or any(
                value is not None for value in supplied_binding
            ):
                return False
        elif not (
            isinstance(bound_catalog_item_id, str)
            and bool(bound_catalog_item_id)
            and isinstance(bound_content_lease_token, str)
            and bool(bound_content_lease_token)
            and type(bound_item_work_unit_deadline_at) is int
            and int(bound_item_work_unit_deadline_at) > int(now)
            and type(bound_logical_attempt) is int
            and bound_logical_attempt in {1, 2}
            and isinstance(bound_content_phase, str)
            and bool(bound_content_phase)
            and hint.get("bound_content_attempt_ordinal")
            == bound_logical_attempt
            and str(hint.get("bound_content_phase") or "")
            == bound_content_phase
            and hint.get("hard_deadline_at")
            == bound_item_work_unit_deadline_at
        ):
            return False
        sealed_retry_authority: object | None = None
        coordinator_items: list[DatabaseRow] | None = None
        if work_kind == "coordinator":
            coordinator_items = list(
                conn.execute(
                    """
                    SELECT * FROM learning_catalog_build_items
                    WHERE build_job_id = ?
                    ORDER BY subject_ordinal, boundary_ordinal,
                      variant_ordinal, id
                    """,
                    (catalog_build_id,),
                ).fetchall()
            )
            if (
                len(coordinator_items) != 30
                or any(
                    not self._coordinator_dependency_item_is_pristine(item)
                    for item in coordinator_items
                )
            ):
                return False
            sealed_retry_authority = self.load_parent_retry_authority(
                conn,
                plan=hint,
                lock=False,
            )
            if sealed_retry_authority.authority_class != "pre_provider_dependency":
                return False
        catalog_item_id = str(bound_catalog_item_id or "")
        bound_attempt = hint.get("bound_content_attempt_ordinal")
        bound_phase = str(hint.get("bound_content_phase") or "")
        dispatch_identity = (
            (bound_attempt, bound_phase)
            if catalog_item_id
            and type(bound_attempt) is int
            and bound_phase
            else None
        )
        dependency_authority: list[object] = []
        authority = self._lock_shared_authority(
            conn,
            plan_id=plan_id,
            catalog_build_id=catalog_build_id,
            catalog_release_id=catalog_release_id,
            catalog_item_id=catalog_item_id or None,
            reject_dispatch_identity=dispatch_identity,
            provider_dependency_identity=(
                dispatch_identity if work_kind == "provider_phase" else None
            ),
            host_dependency_identity=(
                dispatch_identity if work_kind == "host_gate" else None
            ),
            dependency_authority_out=dependency_authority,
        )
        if authority is None:
            return False
        release, build, items, child, plan = authority
        if work_kind == "host_gate":
            sealed_retry_authority = (
                dependency_authority[0] if dependency_authority else None
            )
        if not self._shared_authority_matches(
            release=release,
            build=build,
            items=coordinator_items if work_kind == "coordinator" else None,
            child=child,
            plan=plan,
            target_fingerprint=target_fingerprint,
        ):
            return False
        if not self._active_content_build_matches(
            build,
            require_running=work_kind != "coordinator",
        ):
            return False
        if any(
            plan.get(field) != hint.get(field)
            for field in (
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
                "status",
                "stage",
                "lease_token",
                "hard_deadline_at",
                "work_unit_kind",
                "bound_catalog_item_id",
                "bound_content_attempt_ordinal",
                "bound_content_phase",
            )
        ):
            return False
        if not self._claim_matches(
            plan,
            lease_token=plan_lease_token,
            target_fingerprint=target_fingerprint,
            expected_stage=expected_stage,
            now=now,
        ):
            return False
        if not self._is_v2_plan(plan) or expected_stage not in {
            "planning",
            "generating_content",
        }:
            return False
        deadline = int(plan.get("hard_deadline_at") or 0)
        if int(next_run_at) > deadline:
            raise ValueError("dependency retry cannot exceed its original deadline")
        if str(plan.get("work_unit_kind") or "") not in {
            "coordinator",
            "provider_phase",
            "host_gate",
        }:
            return False
        if not self._dependency_retry_binding_matches(
            release=release,
            build=build,
            plan=plan,
            items=items,
            now=now,
            sealed_retry_authority=sealed_retry_authority,
            bound_content_lease_token=bound_content_lease_token,
            bound_item_work_unit_deadline_at=bound_item_work_unit_deadline_at,
        ):
            return False
        cursor = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET status = 'queued', stage = 'retry_wait',
              resume_stage = ?, lease_token = NULL, lease_expires_at = NULL,
              heartbeat_at = NULL, next_run_at = ?,
              retry_reason_code = 'preparation_dependency_unavailable',
              retry_message_safe = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND stage = ?
              AND lease_token = ? AND target_fingerprint = ?
              AND hard_deadline_at = ? AND hard_deadline_at > ?
              AND lease_expires_at > ?
              AND work_unit_kind = ?
              AND bound_catalog_item_id <=> ?
              AND bound_content_attempt_ordinal <=> ?
              AND bound_content_phase <=> ?
            """,
            (
                expected_stage,
                int(next_run_at),
                self.PUBLIC_FAILURES["preparation_dependency_unavailable"],
                int(now),
                plan_id,
                expected_stage,
                plan_lease_token,
                target_fingerprint,
                deadline,
                int(now),
                int(now),
                work_kind,
                plan.get("bound_catalog_item_id"),
                plan.get("bound_content_attempt_ordinal"),
                plan.get("bound_content_phase"),
            ),
        )
        return cursor.rowcount == 1

    def reconcile_shared_build(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        target_fingerprint: str,
        now: int,
        owner_plan_id: str | None = None,
        owner_lease_token: str | None = None,
    ) -> int:
        return self._reconcile_shared_build_locked(
            conn,
            build_id=build_id,
            target_fingerprint=target_fingerprint,
            now=now,
            owner_plan_id=owner_plan_id,
            owner_lease_token=owner_lease_token,
        )

    def recover_shared_content_validation_plans(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        target_fingerprint: str,
        now: int,
    ) -> int:
        """Reopen exact failed fanout after an atomic Host checkpoint recovery."""
        self._validate_identifier(build_id, "build_id")
        self._require_timestamp(now, "now")
        if re.fullmatch(r"[0-9a-f]{64}", target_fingerprint) is None:
            raise ValueError("target_fingerprint must be canonical SHA-256")
        expected_build_id = "catalog_build_" + hashlib.sha256(
            f"grade-build:{target_fingerprint}".encode("utf-8")
        ).hexdigest()[:24]
        if build_id != expected_build_id:
            return 0
        build = conn.execute(
            "SELECT * FROM learning_catalog_build_jobs WHERE id = ? FOR UPDATE",
            (build_id,),
        ).fetchone()
        items = list(
            conn.execute(
                "SELECT * FROM learning_catalog_build_items "
                "WHERE build_job_id = ? ORDER BY id FOR UPDATE",
                (build_id,),
            ).fetchall()
        )
        plans = list(
            conn.execute(
                "SELECT * FROM learning_curriculum_preparation_plans "
                "WHERE catalog_build_id = ? AND target_fingerprint = ? "
                "ORDER BY id FOR UPDATE",
                (build_id, target_fingerprint),
            ).fetchall()
        )
        current_target = build_preparation_target("primary_1")
        try:
            plan_targets = [
                json.loads(str(plan["target_spec_json"])) for plan in plans
            ]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return 0
        if not (
            build is not None
            and str(build.get("status") or "") == "running"
            and build.get("error_code") is None
            and build.get("completed_at") is None
            and len(items) == 30
            and sum(str(item.get("status") or "") == "processing" for item in items)
            == 1
            and not any(str(item.get("status") or "") == "failed" for item in items)
            and plans
            and all(
                str(plan.get("grade_code") or "") == "primary_1"
                and str(plan.get("status") or "") == "failed"
                and str(plan.get("stage") or "") == "completed"
                and str(plan.get("error_code") or "")
                == "preparation_content_validation_failed"
                and plan.get("completed_at") is not None
                and compatible_preparation_target(plan_target, current_target)
                and preparation_target_fingerprint(plan_target) == target_fingerprint
                and plan.get("superseded_at") is None
                and all(
                    plan.get(field) is None
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
                    )
                )
                for plan, plan_target in zip(plans, plan_targets)
            )
        ):
            return 0
        updated = 0
        for plan in plans:
            cursor = conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET status = 'running', stage = 'generating_content',
                  next_run_at = ?, error_code = NULL,
                  error_message_safe = NULL, completed_at = NULL,
                  last_progress_at = ?, updated_at = ?
                WHERE id = ? AND status = 'failed' AND stage = 'completed'
                  AND target_fingerprint = ? AND catalog_build_id = ?
                  AND error_code = 'preparation_content_validation_failed'
                  AND completed_at IS NOT NULL AND superseded_at IS NULL
                  AND lease_token IS NULL AND lease_expires_at IS NULL
                  AND heartbeat_at IS NULL AND next_run_at IS NULL
                  AND hard_deadline_at IS NULL AND resume_stage IS NULL
                  AND work_unit_kind IS NULL AND bound_catalog_item_id IS NULL
                  AND bound_content_attempt_ordinal IS NULL
                  AND bound_content_phase IS NULL
                """,
                (
                    int(now),
                    int(now),
                    int(now),
                    plan["id"],
                    target_fingerprint,
                    build_id,
                ),
            )
            if cursor.rowcount != 1:
                raise LearningCurriculumPreparationConflict(
                    "shared content recovery plan CAS drift"
                )
            updated += 1
        return updated

    def recover_shared_content_audit_plans(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        target_fingerprint: str,
        now: int,
    ) -> int:
        """Reopen exact fanout after a corrected full-inventory audit replay."""

        self._validate_identifier(build_id, "build_id")
        self._require_timestamp(now, "now")
        if re.fullmatch(r"[0-9a-f]{64}", target_fingerprint) is None:
            raise ValueError("target_fingerprint must be canonical SHA-256")
        expected_build_id = "catalog_build_" + hashlib.sha256(
            f"grade-build:{target_fingerprint}".encode("utf-8")
        ).hexdigest()[:24]
        if build_id != expected_build_id:
            return 0
        build = conn.execute(
            "SELECT * FROM learning_catalog_build_jobs WHERE id = ? FOR UPDATE",
            (build_id,),
        ).fetchone()
        items = list(
            conn.execute(
                "SELECT * FROM learning_catalog_build_items "
                "WHERE build_job_id = ? ORDER BY id FOR UPDATE",
                (build_id,),
            ).fetchall()
        )
        plans = list(
            conn.execute(
                "SELECT * FROM learning_curriculum_preparation_plans "
                "WHERE catalog_build_id = ? AND target_fingerprint = ? "
                "ORDER BY id FOR UPDATE",
                (build_id, target_fingerprint),
            ).fetchall()
        )
        current_target = build_preparation_target("primary_1")
        try:
            plan_targets = [
                json.loads(str(plan["target_spec_json"])) for plan in plans
            ]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return 0
        if not (
            build is not None
            and str(build.get("status") or "") == "running"
            and build.get("error_code") is None
            and build.get("completed_at") is None
            and len(items) == 30
            and 1 <= sum(
                str(item.get("status") or "") == "course_ready"
                for item in items
            ) < 30
            and any(str(item.get("status") or "") == "pending" for item in items)
            and all(
                str(item.get("status") or "") in {"pending", "course_ready"}
                for item in items
            )
            and plans
            and all(
                str(plan.get("grade_code") or "") == "primary_1"
                and str(plan.get("status") or "") == "failed"
                and str(plan.get("stage") or "") == "completed"
                and str(plan.get("error_code") or "")
                == "preparation_content_contract_drift"
                and plan.get("completed_at") is not None
                and compatible_preparation_target(plan_target, current_target)
                and preparation_target_fingerprint(plan_target) == target_fingerprint
                and plan.get("superseded_at") is None
                and all(
                    plan.get(field) is None
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
                    )
                )
                for plan, plan_target in zip(plans, plan_targets)
            )
        ):
            return 0
        updated = 0
        for plan in plans:
            cursor = conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET status = 'running', stage = 'generating_content',
                  next_run_at = ?, error_code = NULL,
                  error_message_safe = NULL, completed_at = NULL,
                  last_progress_at = ?, updated_at = ?
                WHERE id = ? AND status = 'failed' AND stage = 'completed'
                  AND target_fingerprint = ? AND catalog_build_id = ?
                  AND error_code = 'preparation_content_contract_drift'
                  AND completed_at IS NOT NULL AND superseded_at IS NULL
                  AND lease_token IS NULL AND lease_expires_at IS NULL
                  AND heartbeat_at IS NULL AND next_run_at IS NULL
                  AND hard_deadline_at IS NULL AND resume_stage IS NULL
                  AND work_unit_kind IS NULL AND bound_catalog_item_id IS NULL
                  AND bound_content_attempt_ordinal IS NULL
                  AND bound_content_phase IS NULL
                """,
                (
                    int(now),
                    int(now),
                    int(now),
                    plan["id"],
                    target_fingerprint,
                    build_id,
                ),
            )
            if cursor.rowcount != 1:
                raise LearningCurriculumPreparationConflict(
                    "shared content audit recovery plan CAS drift"
                )
            updated += 1
        return updated

    def reconcile_shared_build_with_owner_outcome(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        target_fingerprint: str,
        now: int,
        owner_plan_id: str,
        owner_lease_token: str,
    ) -> SharedBuildReconciliationSnapshot:
        outcome = [False]
        updated = self._reconcile_shared_build_locked(
            conn,
            build_id=build_id,
            target_fingerprint=target_fingerprint,
            now=now,
            owner_plan_id=owner_plan_id,
            owner_lease_token=owner_lease_token,
            owner_handoff_outcome=outcome,
        )
        return SharedBuildReconciliationSnapshot(
            updated_count=updated,
            exact_owner_handoff=outcome[0],
        )

    def shared_build_handoff_owner_complete(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        target_fingerprint: str,
        catalog_build_id: str,
        catalog_release_id: str,
    ) -> bool:
        self._validate_identifier(plan_id, "plan_id")
        self._validate_identifier(catalog_build_id, "catalog_build_id")
        self._validate_identifier(catalog_release_id, "catalog_release_id")
        plan = self.get_plan(conn, plan_id, for_update=True)
        if plan is None:
            return False
        try:
            subject_progress = json.loads(str(plan["subject_progress_json"]))
            self._validate_progress_counts(
                plan,
                ready_course_count=0,
                failed_course_count=0,
                subject_progress=subject_progress,
                monotonic=False,
            )
            stage_progress = json.loads(str(plan["stage_progress_json"]))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return False
        return bool(
            str(plan.get("target_fingerprint") or "") == target_fingerprint
            and str(plan.get("catalog_build_id") or "") == catalog_build_id
            and str(plan.get("catalog_release_id") or "") == catalog_release_id
            and str(plan.get("status") or "") == "running"
            and str(plan.get("stage") or "") == "building_classrooms"
            and type(plan.get("content_target_count")) is int
            and int(plan["content_target_count"]) == 30
            and type(plan.get("content_candidate_count")) is int
            and int(plan["content_candidate_count"]) == 30
            and type(plan.get("content_failed_count")) is int
            and int(plan["content_failed_count"]) == 0
            and type(plan.get("content_canary_target_count")) is int
            and int(plan["content_canary_target_count"]) == 3
            and type(plan.get("content_canary_candidate_count")) is int
            and int(plan["content_canary_candidate_count"]) == 3
            and type(plan.get("content_canary_failed_count")) is int
            and int(plan["content_canary_failed_count"]) == 0
            and type(plan.get("progress_percent")) is int
            and int(plan["progress_percent"]) == 35
            and type(plan.get("ready_course_count")) is int
            and int(plan["ready_course_count"]) == 0
            and type(plan.get("failed_course_count")) is int
            and int(plan["failed_course_count"]) == 0
            and stage_progress
            == {
                "candidateCount": 30,
                "canaryCandidateCount": 3,
                "canaryFailedCount": 0,
                "canaryTargetCount": 3,
                "failedCount": 0,
                "targetCount": 30,
            }
            and all(
                plan.get(field) is None
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
                )
            )
        )

    def fail_shared_build_plans(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        target_fingerprint: str,
        now: int,
    ) -> int:
        return self._reconcile_shared_build_locked(
            conn,
            build_id=build_id,
            target_fingerprint=target_fingerprint,
            now=now,
            require_terminal=True,
        )

    def count_runner_scope(
        self,
        conn: DatabaseConnection,
        *,
        now: int,
        supported_stages: Sequence[str],
        grade_code: str | None = None,
        target_fingerprint: str | None = None,
    ) -> Mapping[str, int]:
        self._require_timestamp(now, "now")
        stages = self._supported_stages(supported_stages)
        if not stages:
            return {
                "claimablePlanCount": 0,
                "runningPlanCount": 0,
                "expiredLeaseCount": 0,
            }
        scope_clause, scope_params = self._runner_target_scope(grade_code, target_fingerprint)
        work_stages = tuple(stage for stage in stages if stage != "queued")
        stage_markers = ", ".join("?" for _ in stages)
        resume_clause = ""
        params: list[object] = [int(now), int(now), *stages]
        if work_stages:
            resume_markers = ", ".join("?" for _ in work_stages)
            resume_clause = (
                f"OR (stage = 'retry_wait' AND resume_stage IN ({resume_markers}))"
            )
            params.extend(work_stages)
        claimable = conn.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM learning_curriculum_preparation_plans
            WHERE status IN ('queued', 'running')
              AND next_run_at <= ?
              AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
              AND (stage IN ({stage_markers}) {resume_clause})
              {scope_clause}
            """,
            (*params, *scope_params),
        ).fetchone()
        running_markers = ", ".join("?" for _ in work_stages)
        running = (
            conn.execute(
                f"""
                SELECT COUNT(*) AS count
                FROM learning_curriculum_preparation_plans
                WHERE status = 'running' AND stage IN ({running_markers})
                  {scope_clause}
                """,
                (*work_stages, *scope_params),
            ).fetchone()
            if work_stages
            else {"count": 0}
        )
        expired = conn.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM learning_curriculum_preparation_plans
            WHERE status = 'running' AND lease_token IS NOT NULL
              AND lease_expires_at <= ?
              AND stage IN ({running_markers})
              {scope_clause}
            """,
            (int(now), *work_stages, *scope_params),
        ).fetchone() if work_stages else {"count": 0}
        return {
            "claimablePlanCount": int(claimable["count"]),
            "runningPlanCount": int(running["count"]),
            "expiredLeaseCount": int(expired["count"]),
        }

    def load_parent_retry_authority(
        self,
        conn: DatabaseConnection,
        *,
        plan: Mapping[str, object],
        lock: bool,
    ) -> ParentRetryAuthoritySnapshot:
        if not isinstance(plan, Mapping):
            raise ValueError("plan must be a mapping")
        inventory = self._load_parent_retry_catalog_inventory(
            conn,
            plan=plan,
            lock=lock,
        )
        if inventory is None:
            return self._empty_parent_retry_authority()
        build_id = str(plan.get("catalog_build_id") or "")
        release_id = str(plan.get("catalog_release_id") or "")
        auditor = self.content_parent_retry_auditor
        if auditor is None:
            return self._empty_parent_retry_authority()
        try:
            sealed = auditor(inventory=inventory)
        except Exception:
            return self._empty_parent_retry_authority()
        if not (
            isinstance(sealed, ContentParentRetryAuditSnapshot)
            and sealed.build_id == build_id
            and sealed.release_id == release_id
        ):
            return self._empty_parent_retry_authority()
        return ParentRetryAuthoritySnapshot(
            authority_class=sealed.authority_class,
            provider_dispatch_count=len(sealed.provider_dispatch_ids),
            open_or_ambiguous_dispatch_count=len(
                sealed.open_or_ambiguous_dispatch_ids
            ),
            failed_safe_dispatch_count=len(sealed.failed_safe_dispatch_ids),
            provider_graph_complete=sealed.provider_graph_complete,
            next_work_kind=sealed.next_work_kind,
            build_error_code=sealed.build_error_code,
        )

    def _load_parent_retry_catalog_inventory(
        self,
        conn: DatabaseConnection,
        *,
        plan: Mapping[str, object],
        lock: bool,
    ) -> Mapping[str, object] | None:
        build_id = str(plan.get("catalog_build_id") or "")
        release_id = str(plan.get("catalog_release_id") or "")
        if not build_id or not release_id:
            return None
        suffix = " FOR UPDATE" if lock else ""
        release = conn.execute(
            "SELECT * FROM learning_catalog_releases "
            "WHERE id = ? LIMIT 1" + suffix,
            (release_id,),
        ).fetchone()
        build = conn.execute(
            "SELECT * FROM learning_catalog_build_jobs "
            "WHERE id = ? AND release_id = ? LIMIT 1" + suffix,
            (build_id, release_id),
        ).fetchone()
        items = list(
            conn.execute(
                """
                SELECT * FROM learning_catalog_build_items
                WHERE build_job_id = ?
                ORDER BY subject_ordinal, boundary_ordinal,
                  variant_ordinal, id
                """ + suffix,
                (build_id,),
            ).fetchall()
        )
        if release is None or build is None or len(items) != 30:
            return None
        release_item = conn.execute(
            "SELECT release_id FROM learning_catalog_release_items "
            "WHERE release_id = ? LIMIT 1" + suffix,
            (release_id,),
        ).fetchone()
        item_ids = [str(item["id"]) for item in items]
        markers = ", ".join("?" for _ in item_ids)
        dispatches = list(
            conn.execute(
                f"""
                SELECT * FROM learning_course_provider_dispatches
                WHERE build_item_id IN ({markers})
                ORDER BY build_item_id, logical_attempt, phase_ordinal, id
                """ + suffix,
                item_ids,
            ).fetchall()
        )
        histories = self._load_parent_retry_attempt_histories(
            conn,
            items=items,
            dispatches=dispatches,
            lock=lock,
        )
        try:
            historical_fingerprints = {
                str(item["id"]): historical_question_fingerprint_snapshots(
                    conn,
                    item=item,
                    histories=histories.get(str(item["id"]), {}),
                )
                for item in items
                if int(item.get("attempt_count") or 0) > 0
            }
        except ValueError:
            return None
        return {
            "plan": dict(plan),
            "release": dict(release),
            "build": dict(build),
            "items": [dict(item) for item in items],
            "dispatches": [dict(row) for row in dispatches],
            "evidence": [
                {
                    "item": dict(item),
                    "attemptHistories": histories.get(str(item["id"]), {}),
                    "historicalQuestionFingerprintsByAttempt": (
                        historical_fingerprints.get(str(item["id"]), {})
                    ),
                }
                for item in items
                if str(item.get("status") or "")
                in {"course_ready", "failed"}
            ],
            "attemptHistoriesByItem": histories,
            "historicalQuestionFingerprintsByItem": historical_fingerprints,
            "releaseHasCatalogItems": release_item is not None,
        }

    def lock_parent_retry_context(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        plan_id: str,
    ) -> tuple[DatabaseRow, DatabaseRow, ParentRetryAuthoritySnapshot] | None:
        hint = conn.execute(
            """
            SELECT * FROM learning_curriculum_preparation_plans
            WHERE id = ? AND family_id = ? LIMIT 1
            """,
            (plan_id, family_id),
        ).fetchone()
        if hint is None:
            return None
        snapshot = self.load_parent_retry_authority(
            conn, plan=hint, lock=True
        )
        family = conn.execute(
            "SELECT * FROM families WHERE id = ? LIMIT 1 FOR UPDATE",
            (family_id,),
        ).fetchone()
        child = conn.execute(
            """
            SELECT * FROM children
            WHERE id = ? AND family_id = ? LIMIT 1 FOR UPDATE
            """,
            (hint["child_id"], family_id),
        ).fetchone()
        locked_plan = self.get_plan(conn, plan_id, for_update=True)
        if family is None or child is None or locked_plan is None:
            return None
        immutable = (
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
        if any(locked_plan.get(key) != hint.get(key) for key in immutable):
            return None
        return child, locked_plan, snapshot

    def apply_stage_result(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        lease_token: str,
        target_fingerprint: str,
        expected_stage: str,
        next_status: str,
        next_stage: str,
        ready_course_count: int,
        failed_course_count: int,
        subject_progress: Mapping[str, Any],
        next_run_at: int | None,
        hard_deadline_at: int | None,
        catalog_build_id: str | None,
        catalog_release_id: str | None,
        now: int,
    ) -> bool:
        plan = self.get_plan(conn, plan_id, for_update=True)
        if not self._claim_matches(
            plan,
            lease_token=lease_token,
            target_fingerprint=target_fingerprint,
            expected_stage=expected_stage,
            now=now,
        ):
            return False
        self._validate_progress_counts(
            plan,
            ready_course_count=ready_course_count,
            failed_course_count=failed_course_count,
            subject_progress=subject_progress,
            monotonic=True,
        )
        build_id = catalog_build_id or plan.get("catalog_build_id")
        release_id = catalog_release_id or plan.get("catalog_release_id")
        if plan.get("catalog_build_id") not in (None, build_id):
            raise ValueError("catalog build identity cannot change")
        if plan.get("catalog_release_id") not in (None, release_id):
            raise ValueError("catalog release identity cannot change")
        formal_handoff = bool(
            self._is_v2_plan(plan)
            and expected_stage
            in {"building_classrooms", "generating_speech", "validating"}
            and next_status == "queued"
            and self.ALLOWED_TRANSITIONS.get(expected_stage) == next_stage
        )

        if next_status == "ready":
            if next_stage != "completed" or expected_stage != "publishing":
                raise ValueError("invalid ready preparation transition")
            if self._is_v2_plan(plan):
                raise ValueError(
                    "formal V2 readiness requires publication receipts"
                )
            if int(ready_course_count) != int(plan["total_course_count"]):
                raise ValueError("ready preparation must contain every course")
            if int(failed_course_count) != 0:
                raise ValueError("ready preparation cannot contain failed courses")
            stored_status = "ready"
            stored_stage = "completed"
            stored_resume = None
            stored_next_run = None
            stored_deadline = None
            progress = 100
            completed_at = int(now)
            keep_lease = False
        elif formal_handoff:
            if next_run_at is None or hard_deadline_at is not None:
                raise ValueError(
                    "formal stage handoff requires a schedule without a deadline"
                )
            if int(next_run_at) < int(now):
                raise ValueError("formal stage handoff cannot schedule in the past")
            stored_status = "running"
            stored_stage = next_stage
            stored_resume = None
            stored_next_run = int(next_run_at)
            stored_deadline = None
            progress = self._progress_percent(
                next_stage,
                ready_course_count=int(ready_course_count),
                failed_course_count=int(failed_course_count),
                total_course_count=int(plan["total_course_count"]),
                previous=int(plan["progress_percent"]),
            )
            completed_at = None
            keep_lease = False
        else:
            if next_status not in {"queued", "running"}:
                raise ValueError("unsupported nonterminal preparation status")
            if next_status == "running":
                if next_stage != expected_stage:
                    raise ValueError("a running result must remain in the claimed stage")
                stored_status = "running"
                stored_stage = next_stage
                stored_resume = None
                keep_lease = True
            else:
                if self.ALLOWED_TRANSITIONS.get(expected_stage) != next_stage:
                    raise ValueError("invalid preparation stage transition")
                stored_status = "queued"
                stored_stage = "retry_wait"
                stored_resume = next_stage
                keep_lease = False
            if next_run_at is None or hard_deadline_at is None:
                raise ValueError("nonterminal result requires schedule and deadline")
            if int(next_run_at) > int(hard_deadline_at):
                raise ValueError("next run cannot exceed the stage deadline")
            if next_status == "running" and int(hard_deadline_at) != int(plan["hard_deadline_at"]):
                raise ValueError("same-stage result cannot move its deadline")
            stored_next_run = int(next_run_at)
            stored_deadline = int(hard_deadline_at)
            progress = self._progress_percent(
                next_stage,
                ready_course_count=int(ready_course_count),
                failed_course_count=int(failed_course_count),
                total_course_count=int(plan["total_course_count"]),
                previous=int(plan["progress_percent"]),
            )
            completed_at = None

        clear_formal_authority = formal_handoff
        stored_work_unit_kind = (
            None if clear_formal_authority else plan.get("work_unit_kind")
        )
        stored_bound_item_id = (
            None if clear_formal_authority else plan.get("bound_catalog_item_id")
        )
        stored_bound_attempt = (
            None
            if clear_formal_authority
            else plan.get("bound_content_attempt_ordinal")
        )
        stored_bound_phase = (
            None if clear_formal_authority else plan.get("bound_content_phase")
        )
        stored_retry_reason = (
            None if clear_formal_authority else plan.get("retry_reason_code")
        )
        stored_retry_message = (
            None if clear_formal_authority else plan.get("retry_message_safe")
        )

        cursor = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET status = ?, stage = ?, resume_stage = ?,
              ready_course_count = ?, failed_course_count = ?,
              progress_percent = ?, subject_progress_json = ?,
              catalog_build_id = ?, catalog_release_id = ?, next_run_at = ?,
              hard_deadline_at = ?, completed_at = ?,
              lease_token = ?, lease_expires_at = ?, heartbeat_at = ?,
              work_unit_kind = ?, bound_catalog_item_id = ?,
              bound_content_attempt_ordinal = ?, bound_content_phase = ?,
              retry_reason_code = ?, retry_message_safe = ?,
              error_code = NULL, error_message_safe = NULL,
              last_progress_at = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND stage = ?
              AND lease_token = ? AND target_fingerprint = ?
              AND lease_expires_at > ?
            """,
            (
                stored_status,
                stored_stage,
                stored_resume,
                int(ready_course_count),
                int(failed_course_count),
                progress,
                self._encode_json(subject_progress),
                build_id,
                release_id,
                stored_next_run,
                stored_deadline,
                completed_at,
                lease_token if keep_lease else None,
                plan["lease_expires_at"] if keep_lease else None,
                plan["heartbeat_at"] if keep_lease else None,
                stored_work_unit_kind,
                stored_bound_item_id,
                stored_bound_attempt,
                stored_bound_phase,
                stored_retry_reason,
                stored_retry_message,
                int(now),
                int(now),
                plan_id,
                expected_stage,
                lease_token,
                target_fingerprint,
                int(now),
            ),
        )
        if cursor.rowcount != 1:
            return False
        self.append_event(
            conn,
            plan_id=plan_id,
            event_type="stage_result_applied",
            stage=stored_stage,
            payload={
                "fromStage": expected_stage,
                "toStage": stored_stage,
                "status": stored_status,
                "readyCourseCount": int(ready_course_count),
                "failedCourseCount": int(failed_course_count),
                "progressPercent": progress,
            },
            now=now,
        )
        return True

    def defer_claim(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        lease_token: str,
        target_fingerprint: str,
        expected_stage: str,
        next_run_at: int,
        error_code: str,
        now: int,
    ) -> bool:
        plan = self.get_plan(conn, plan_id, for_update=True)
        if not self._claim_matches(
            plan,
            lease_token=lease_token,
            target_fingerprint=target_fingerprint,
            expected_stage=expected_stage,
            now=now,
        ):
            return False
        deadline = int(plan["hard_deadline_at"])
        if int(next_run_at) > deadline:
            raise ValueError("retry cannot exceed the stage deadline")
        if error_code != "preparation_dependency_unavailable":
            raise ValueError("unsupported preparation retry code")
        cursor = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET status = 'queued', stage = 'retry_wait', resume_stage = ?,
              lease_token = NULL, lease_expires_at = NULL, heartbeat_at = NULL,
              next_run_at = ?, retry_reason_code = ?, retry_message_safe = ?,
              updated_at = ?
            WHERE id = ? AND status = 'running' AND stage = ?
              AND lease_token = ? AND target_fingerprint = ?
              AND lease_expires_at > ?
            """,
            (
                expected_stage,
                int(next_run_at),
                error_code,
                self.PUBLIC_FAILURES[error_code],
                int(now),
                plan_id,
                expected_stage,
                lease_token,
                target_fingerprint,
                int(now),
            ),
        )
        if cursor.rowcount != 1:
            return False
        self.append_event(
            conn,
            plan_id=plan_id,
            event_type="claim_deferred",
            stage="retry_wait",
            payload={
                "stage": expected_stage,
                "code": error_code,
            },
            now=now,
        )
        return True

    def fail_claim(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        lease_token: str,
        target_fingerprint: str,
        expected_stage: str,
        error_code: str,
        error_message_safe: str,
        now: int,
    ) -> bool:
        plan = self.get_plan(conn, plan_id, for_update=True)
        if not (
            plan is not None
            and str(plan["status"]) == "running"
            and str(plan["stage"]) == expected_stage
            and str(plan["lease_token"] or "") == lease_token
            and str(plan["target_fingerprint"]) == target_fingerprint
        ):
            return False
        fixed_message = self.PUBLIC_FAILURES.get(error_code)
        if fixed_message is None or error_message_safe != fixed_message:
            raise ValueError("preparation failure must use a fixed public code/message")
        ready_course_count = int(plan["ready_course_count"])
        failed_course_count = int(plan["failed_course_count"])
        try:
            subject_progress = self._safe_failure_subject_progress(plan)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            canonical_plan = dict(plan)
            canonical_plan["target_spec_json"] = self._encode_json(
                build_preparation_target("primary_1"),
                sort_keys=True,
            )
            canonical_plan["grade_code"] = "primary_1"
            subject_progress = self._safe_failure_subject_progress(canonical_plan)
        progress = self._progress_percent(
            expected_stage,
            ready_course_count=int(ready_course_count),
            failed_course_count=int(failed_course_count),
            total_course_count=int(plan["total_course_count"]),
            previous=int(plan["progress_percent"]),
        )
        cursor = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET status = 'failed', stage = 'completed',
              ready_course_count = ?, failed_course_count = ?,
              progress_percent = ?, subject_progress_json = ?,
              error_code = ?, error_message_safe = ?, completed_at = ?,
              lease_token = NULL, lease_expires_at = NULL, heartbeat_at = NULL,
              next_run_at = NULL, hard_deadline_at = NULL, resume_stage = NULL,
              work_unit_kind = NULL, bound_catalog_item_id = NULL,
              bound_content_attempt_ordinal = NULL, bound_content_phase = NULL,
              retry_reason_code = NULL, retry_message_safe = NULL,
              last_progress_at = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND stage = ?
              AND lease_token = ? AND target_fingerprint = ?
            """,
            (
                int(ready_course_count),
                int(failed_course_count),
                progress,
                self._encode_json(subject_progress),
                error_code,
                fixed_message,
                int(now),
                int(now),
                int(now),
                plan_id,
                expected_stage,
                lease_token,
                target_fingerprint,
            ),
        )
        if cursor.rowcount != 1:
            return False
        self.append_event(
            conn,
            plan_id=plan_id,
            event_type="claim_failed",
            stage="completed",
            payload={"fromStage": expected_stage, "errorCode": error_code},
            now=now,
        )
        return True

    def _fail_invalid_v2_claim_locked(
        self,
        conn: DatabaseConnection,
        *,
        plan: Mapping[str, object],
        failure_stage: str,
        now: int,
    ) -> None:
        plan_id = str(plan.get("id") or "")
        self._validate_identifier(plan_id, "plan_id")
        ready_course_count = int(plan.get("ready_course_count") or 0)
        failed_course_count = int(plan.get("failed_course_count") or 0)
        try:
            subject_progress = self._safe_failure_subject_progress(plan)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            canonical_plan = dict(plan)
            canonical_plan["target_spec_json"] = self._encode_json(
                build_preparation_target("primary_1"),
                sort_keys=True,
            )
            canonical_plan["grade_code"] = "primary_1"
            subject_progress = self._safe_failure_subject_progress(canonical_plan)
        progress = self._progress_percent(
            failure_stage,
            ready_course_count=ready_course_count,
            failed_course_count=failed_course_count,
            total_course_count=int(plan.get("total_course_count") or 0),
            previous=int(plan.get("progress_percent") or 0),
        )
        error_code = "preparation_validation_failed"
        cursor = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET status = 'failed', stage = 'completed',
              ready_course_count = ?, failed_course_count = ?,
              progress_percent = ?, subject_progress_json = ?,
              error_code = ?, error_message_safe = ?, completed_at = ?,
              lease_token = NULL, lease_expires_at = NULL, heartbeat_at = NULL,
              next_run_at = NULL, hard_deadline_at = NULL, resume_stage = NULL,
              work_unit_kind = NULL, bound_catalog_item_id = NULL,
              bound_content_attempt_ordinal = NULL, bound_content_phase = NULL,
              retry_reason_code = NULL, retry_message_safe = NULL,
              last_progress_at = ?, updated_at = ?
            WHERE id = ? AND status IN ('queued', 'running')
            """,
            (
                ready_course_count,
                failed_course_count,
                progress,
                self._encode_json(subject_progress),
                error_code,
                self.PUBLIC_FAILURES[error_code],
                int(now),
                int(now),
                int(now),
                plan_id,
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("invalid V2 preparation claim was not fenced")
        self.append_event(
            conn,
            plan_id=plan_id,
            event_type="claim_failed",
            stage="completed",
            payload={"fromStage": failure_stage, "errorCode": error_code},
            now=now,
        )

    @classmethod
    def _safe_failure_subject_progress(
        cls, plan: DatabaseRow
    ) -> dict[str, dict[str, int]]:
        ready = int(plan["ready_course_count"])
        failed = int(plan["failed_course_count"])
        try:
            decoded = json.loads(str(plan["subject_progress_json"]))
            if not isinstance(decoded, Mapping):
                raise ValueError("subject progress is not an object")
            cls._validate_progress_counts(
                plan,
                ready_course_count=ready,
                failed_course_count=failed,
                subject_progress=decoded,
                monotonic=False,
            )
            return {
                subject: dict(decoded[subject]) for subject in PREPARATION_SUBJECTS
            }
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            target = json.loads(str(plan["target_spec_json"]))
            targets = target["subjectTargets"]
            is_v2 = str(target.get("schemaVersion") or "") == TARGET_SCHEMA_V2
            remaining_ready = ready
            remaining_failed = failed
            remaining_content_candidate = (
                int(plan["content_candidate_count"]) if is_v2 else 0
            )
            remaining_content_failed = (
                int(plan["content_failed_count"]) if is_v2 else 0
            )
            if (
                remaining_content_candidate < 0
                or remaining_content_failed < 0
                or remaining_content_candidate + remaining_content_failed
                > int(plan["content_target_count"])
            ):
                raise ValueError("persisted preparation content counts exceed target")
            fallback: dict[str, dict[str, int]] = {}
            for subject in PREPARATION_SUBJECTS:
                total = int(targets[subject]["totalCourseCount"])
                subject_ready = min(total, remaining_ready)
                remaining_ready -= subject_ready
                subject_failed = min(total - subject_ready, remaining_failed)
                remaining_failed -= subject_failed
                fallback[subject] = {
                    "totalCourseCount": total,
                    "readyCourseCount": subject_ready,
                    "failedCourseCount": subject_failed,
                }
                if is_v2:
                    subject_content_candidate = min(
                        total, remaining_content_candidate
                    )
                    remaining_content_candidate -= subject_content_candidate
                    subject_content_failed = min(
                        total - subject_content_candidate,
                        remaining_content_failed,
                    )
                    remaining_content_failed -= subject_content_failed
                    fallback[subject].update(
                        {
                            "contentCandidateCount": subject_content_candidate,
                            "contentFailedCount": subject_content_failed,
                        }
                    )
            if (
                remaining_ready
                or remaining_failed
                or remaining_content_candidate
                or remaining_content_failed
            ):
                raise ValueError("persisted preparation counts exceed target")
            return fallback

    def transition_stage(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        lease_token: str,
        expected_stage: str,
        next_stage: str,
        ready_course_count: int,
        failed_course_count: int,
        subject_progress: Mapping[str, Any],
        now: int,
        hard_deadline_at: int,
    ) -> bool:
        if self.ALLOWED_TRANSITIONS.get(expected_stage) != next_stage:
            return False
        plan = self.get_plan(conn, plan_id)
        if plan is None:
            return False
        self._validate_progress_counts(
            plan,
            ready_course_count=ready_course_count,
            failed_course_count=failed_course_count,
            subject_progress=subject_progress,
            monotonic=True,
        )
        progress = self._progress_percent(
            next_stage,
            ready_course_count=int(ready_course_count),
            failed_course_count=int(failed_course_count),
            total_course_count=int(plan["total_course_count"]),
            previous=int(plan["progress_percent"]),
        )
        cursor = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET stage = ?, ready_course_count = ?, failed_course_count = ?,
              progress_percent = ?, subject_progress_json = ?,
              hard_deadline_at = ?, last_progress_at = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND stage = ?
              AND lease_token = ?
            """,
            (
                next_stage,
                int(ready_course_count),
                int(failed_course_count),
                progress,
                self._encode_json(subject_progress),
                int(hard_deadline_at),
                int(now),
                int(now),
                plan_id,
                expected_stage,
                lease_token,
            ),
        )
        return cursor.rowcount == 1

    def start_next_formal_pipeline(
        self,
        conn: DatabaseConnection,
        *,
        grade_code: str,
        target_fingerprint: str,
        now: int,
    ) -> str | None:
        """Schedule one exact 30/30 checkpoint that Task 8 left inert."""

        scope_clause, scope_params = self._runner_target_scope(grade_code, target_fingerprint)
        candidate = conn.execute(
            f"""
            SELECT id, target_fingerprint FROM learning_curriculum_preparation_plans
            WHERE 1=1 {scope_clause}
              AND status = 'running' AND stage = 'building_classrooms'
              AND progress_percent = 35 AND next_run_at IS NULL
              AND lease_token IS NULL AND hard_deadline_at IS NULL
            ORDER BY created_at, id LIMIT 1 FOR UPDATE SKIP LOCKED
            """,
            scope_params,
        ).fetchone()
        if candidate is None:
            return None
        plan_id = str(candidate["id"])
        return plan_id if self.start_formal_pipeline(
            conn,
            plan_id=plan_id,
            target_fingerprint=str(candidate["target_fingerprint"]),
            now=now,
        ) else None

    def persist_progressive_formal_counts(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        lease_token: str,
        target_fingerprint: str,
        expected_stage: str,
        now: int,
    ) -> int:
        """Advance formal evidence counters from exact per-item publications."""

        if expected_stage not in {
            "generating_content",
            "building_classrooms",
            "generating_speech",
            "validating",
        }:
            raise ValueError("unsupported progressive formal stage")
        plan = self.get_plan(conn, plan_id, for_update=True)
        if not self._claim_matches(
            plan,
            lease_token=lease_token,
            target_fingerprint=target_fingerprint,
            expected_stage=expected_stage,
            now=now,
        ):
            raise ValueError("progressive formal publisher lease is stale")
        release_id = str(plan.get("catalog_release_id") or "")
        build_id = str(plan.get("catalog_build_id") or "")
        release = conn.execute(
            "SELECT * FROM learning_catalog_releases WHERE id = ? "
            "LIMIT 1 FOR UPDATE",
            (release_id,),
        ).fetchone()
        rows = list(
            conn.execute(
                """
                SELECT release_item.*,
                  item.id AS exact_build_item_id,
                  item.build_job_id AS exact_build_id,
                  item.release_id AS exact_item_release_id,
                  item.grade_code AS exact_item_grade_code,
                  item.status AS exact_item_status,
                  item.content_phase AS exact_content_phase,
                  item.content_gate_status AS exact_content_gate_status,
                  receipt.release_id AS exact_receipt_release_id,
                  receipt.grade_code AS exact_receipt_grade_code,
                  receipt.target_fingerprint AS exact_receipt_fingerprint,
                  receipt.publication_status AS exact_publication_status,
                  receipt.publication_receipt_hash AS exact_publication_hash,
                  receipt.published_at AS exact_receipt_published_at
                FROM learning_catalog_release_items AS release_item
                LEFT JOIN learning_catalog_build_items AS item
                  ON item.build_job_id = ?
                 AND item.release_id = release_item.release_id
                 AND item.course_id = release_item.course_id
                 AND item.course_version = release_item.course_version
                 AND item.grade_code = release_item.grade_code
                 AND item.subject = release_item.subject
                 AND item.skill_id = release_item.skill_id
                 AND item.curriculum_version = release_item.curriculum_version
                 AND item.boundary_version = release_item.boundary_version
                 AND item.variant_ordinal = release_item.variant_ordinal
                LEFT JOIN learning_curriculum_classroom_item_receipts AS receipt
                  ON receipt.build_item_id = item.id
                WHERE release_item.release_id = ?
                ORDER BY release_item.subject, release_item.skill_id,
                  release_item.variant_ordinal, release_item.course_id
                FOR UPDATE
                """,
                (build_id, release_id),
            ).fetchall()
        )
        published_count = len(rows)
        if not (
            release is not None
            and release_id
            and build_id
            and str(release.get("status") or "") == "draft"
            and str(release.get("quality_status") or "") == "building"
            and release.get("activated_at") is None
            and release.get("retired_at") is None
            and 1 <= published_count <= int(plan.get("total_course_count") or 0)
            and int(release.get("ready_item_count") or 0) == published_count
            and published_count
            >= int(plan.get("published_course_count") or 0)
            and all(
                str(row.get("exact_build_item_id") or "")
                and str(row.get("exact_build_id") or "") == build_id
                and str(row.get("exact_item_release_id") or "") == release_id
                and str(row.get("exact_item_grade_code") or "")
                == str(plan.get("grade_code") or "")
                and str(row.get("exact_item_status") or "") == "course_ready"
                and str(row.get("exact_content_phase") or "") == "course_ready"
                and str(row.get("exact_content_gate_status") or "") == "passed"
                and str(row.get("status") or "") == "published"
                and str(row.get("quality_status") or "") == "ready"
                and row.get("published_at") is not None
                and row.get("retired_at") is None
                and str(row.get("exact_receipt_release_id") or "") == release_id
                and str(row.get("exact_receipt_grade_code") or "")
                == str(plan.get("grade_code") or "")
                and str(row.get("exact_receipt_fingerprint") or "")
                == target_fingerprint
                and str(row.get("exact_publication_status") or "")
                == "published"
                and re.fullmatch(
                    r"[0-9a-f]{64}",
                    str(row.get("exact_publication_hash") or ""),
                )
                is not None
                and row.get("exact_receipt_published_at") is not None
                for row in rows
            )
        ):
            raise ValueError("progressive formal publication evidence is invalid")
        classroom_ready = max(
            int(plan.get("classroom_ready_count") or 0), published_count
        )
        speech_ready = max(
            int(plan.get("speech_ready_count") or 0), published_count
        )
        validation_ready = max(
            int(plan.get("validation_ready_count") or 0), published_count
        )
        if not (
            published_count <= validation_ready <= speech_ready <= classroom_ready
            <= int(plan["total_course_count"])
        ):
            raise ValueError("progressive formal counters are inconsistent")
        cursor = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET classroom_ready_count = ?, speech_ready_count = ?,
              validation_ready_count = ?, published_course_count = ?,
              last_progress_at = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND stage = ?
              AND lease_token = ? AND target_fingerprint = ?
              AND lease_expires_at > ?
            """,
            (
                classroom_ready,
                speech_ready,
                validation_ready,
                published_count,
                int(now),
                int(now),
                plan_id,
                expected_stage,
                lease_token,
                target_fingerprint,
                int(now),
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError("progressive formal counters could not be persisted")
        self.append_event(
            conn,
            plan_id=plan_id,
            event_type="formal_items_published",
            stage=expected_stage,
            payload={"publishedCourseCount": published_count},
            now=int(now),
        )
        return published_count

    def persist_formal_stage_progress(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        lease_token: str,
        target_fingerprint: str,
        expected_stage: str,
        classroom_ready_count: int,
        speech_ready_count: int,
        next_run_at: int,
        now: int,
    ) -> tuple[bool, str]:
        """Release a formal-stage claim and perform each 30/30 handoff once."""

        if expected_stage not in {"building_classrooms", "generating_speech"}:
            raise ValueError("unsupported formal preparation stage")
        hint = self.get_plan(conn, plan_id)
        if hint is None:
            return False, expected_stage
        release = conn.execute(
            "SELECT * FROM learning_catalog_releases WHERE id = ? "
            "LIMIT 1 FOR UPDATE",
            (hint.get("catalog_release_id"),),
        ).fetchone()
        build = conn.execute(
            "SELECT * FROM learning_catalog_build_jobs WHERE id = ? "
            "LIMIT 1 FOR UPDATE",
            (hint.get("catalog_build_id"),),
        ).fetchone()
        items = conn.execute(
            "SELECT * FROM learning_catalog_build_items WHERE build_job_id = ? "
            "ORDER BY id FOR UPDATE",
            (hint.get("catalog_build_id"),),
        ).fetchall()
        plan = self.get_plan(conn, plan_id, for_update=True)
        if not self._claim_matches(
            plan,
            lease_token=lease_token,
            target_fingerprint=target_fingerprint,
            expected_stage=expected_stage,
            now=now,
        ):
            return False, expected_stage
        if release is None or build is None or len(items) != 30:
            raise ValueError("formal preparation build authority is incomplete")
        try:
            build_target = json.loads(str(build["target_spec_json"]))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("formal preparation build target is invalid") from exc
        if not (
            str(release.get("id") or "")
            == str(plan.get("catalog_release_id") or "")
            == str(build.get("release_id") or "")
            and str(build.get("id") or "")
            == str(plan.get("catalog_build_id") or "")
            and preparation_target_fingerprint(build_target) == target_fingerprint
            and all(
                str(item.get("release_id") or "") == str(release["id"])
                and str(item.get("grade_code") or "") == str(plan["grade_code"])
                and str(item.get("execution_mode_snapshot") or "") == "content_only"
                and str(item.get("content_phase") or "") == "course_ready"
                and str(item.get("content_gate_status") or "") == "passed"
                and item.get("package_id") is None
                and item.get("package_version") is None
                for item in items
            )
        ):
            raise ValueError("formal preparation build authority is stale")
        item_ids = [str(item["id"]) for item in items]
        markers = ", ".join("?" for _ in item_ids)
        runtimes = conn.execute(
            f"SELECT * FROM learning_openmaic_runtime_classrooms "
            f"WHERE candidate_build_item_id IN ({markers}) "
            "ORDER BY candidate_build_item_id, attempt_ordinal FOR UPDATE",
            item_ids,
        ).fetchall()
        receipts = conn.execute(
            f"SELECT * FROM learning_curriculum_classroom_item_receipts "
            f"WHERE build_item_id IN ({markers}) ORDER BY build_item_id FOR UPDATE",
            item_ids,
        ).fetchall()
        audio_jobs = conn.execute(
            f"SELECT * FROM learning_formal_qwen_audio_jobs "
            f"WHERE build_item_id IN ({markers}) ORDER BY build_item_id FOR UPDATE",
            item_ids,
        ).fetchall()
        runtime_by_id = {str(row["id"]): row for row in runtimes}
        receipt_by_item = {str(row["build_item_id"]): row for row in receipts}
        audio_by_item = {str(row["build_item_id"]): row for row in audio_jobs}
        authoritative_classrooms = 0
        authoritative_speech = 0
        formal_failed = 0
        for item in items:
            item_id = str(item["id"])
            receipt = receipt_by_item.get(item_id)
            runtime = (
                runtime_by_id.get(str(receipt.get("runtime_classroom_id") or ""))
                if receipt is not None
                else None
            )
            audio = audio_by_item.get(item_id)
            runtime_manifest: Mapping[str, Any] = {}
            if runtime is not None:
                raw_manifest = runtime.get("feature_manifest_json")
                if isinstance(raw_manifest, Mapping):
                    runtime_manifest = raw_manifest
                elif isinstance(raw_manifest, str):
                    try:
                        decoded_manifest = json.loads(raw_manifest)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        decoded_manifest = None
                    if isinstance(decoded_manifest, Mapping):
                        runtime_manifest = decoded_manifest
            formal_evidence = runtime_manifest.get("formalEvidence")
            runtime_scene_count = runtime_manifest.get("sceneCount")
            runtime_speech_action_count = (
                formal_evidence.get("speechActionCount")
                if isinstance(formal_evidence, Mapping)
                else None
            )
            classroom_exact = bool(
                receipt is not None
                and runtime is not None
                and str(receipt.get("classroom_status") or "") == "passed"
                and str(receipt.get("release_id") or "") == str(release["id"])
                and str(receipt.get("grade_code") or "") == str(plan["grade_code"])
                and str(receipt.get("target_fingerprint") or "")
                == target_fingerprint
                and str(receipt.get("binding_contract_version") or "")
                == self.CANDIDATE_BINDING_CONTRACT_VERSION
                and str(runtime.get("status") or "") == "ready"
                and str(runtime.get("candidate_build_item_id") or "") == item_id
                and str(runtime.get("candidate_release_id") or "")
                == str(release["id"])
                and str(runtime.get("candidate_grade_code") or "")
                == str(plan["grade_code"])
                and str(runtime.get("candidate_target_fingerprint") or "")
                == target_fingerprint
                and str(runtime.get("candidate_binding_contract_version") or "")
                == self.CANDIDATE_BINDING_CONTRACT_VERSION
                and str(runtime.get("course_id") or "")
                == str(item.get("course_id") or "")
                == str(receipt.get("course_id") or "")
                and str(runtime.get("course_version") or "")
                == str(item.get("course_version") or "")
                == str(receipt.get("course_version") or "")
                and str(runtime.get("package_id") or "")
                == str(receipt.get("package_id") or "")
                and int(runtime.get("package_version") or 0)
                == int(receipt.get("package_version") or 0) > 0
            )
            authoritative_classrooms += int(classroom_exact)
            expected_segment_count = int(
                audio.get("expected_segment_count") or 0
            ) if audio is not None else 0
            speech_exact = bool(
                classroom_exact
                and audio is not None
                and str(audio.get("state") or "") == "auto_validated"
                and str(audio.get("release_id") or "") == str(release["id"])
                and str(audio.get("grade_code") or "") == str(plan["grade_code"])
                and str(audio.get("target_fingerprint") or "")
                == target_fingerprint
                and str(audio.get("runtime_classroom_id") or "")
                == str(runtime.get("id") or "")
                and str(audio.get("course_id") or "")
                == str(receipt.get("course_id") or "")
                and str(audio.get("course_version") or "")
                == str(receipt.get("course_version") or "")
                and str(audio.get("package_id") or "")
                == str(receipt.get("package_id") or "")
                and int(audio.get("package_version") or 0)
                == int(receipt.get("package_version") or 0)
                and 1 <= expected_segment_count <= 240
                and type(runtime_scene_count) is int
                and 1 <= runtime_scene_count <= 60
                and type(runtime_speech_action_count) is int
                and runtime_scene_count
                <= runtime_speech_action_count
                <= min(240, runtime_scene_count * 20)
                and expected_segment_count == runtime_speech_action_count
                and int(audio.get("tts_attempted_count") or 0)
                == expected_segment_count
                and int(audio.get("tts_completed_count") or 0)
                == expected_segment_count
                and int(audio.get("audio_validated_count") or 0)
                == expected_segment_count
                and int(audio.get("asr_attempted_count") or 0)
                == expected_segment_count
                and int(audio.get("asr_passed_count") or 0)
                == expected_segment_count
                and re.fullmatch(
                    r"[0-9a-f]{64}",
                    str(audio.get("terminal_receipt_hash") or ""),
                ) is not None
                and str(receipt.get("tts_status") or "") == "passed"
                and str(receipt.get("asr_roundtrip_status") or "") == "passed"
                and int(receipt.get("approved") or 0) == 0
                and (
                    int(receipt.get("auto_validated") or 0) == 0
                    or (
                        int(receipt.get("auto_validated") or 0) == 1
                        and str(
                            receipt.get("conversation_provider_status") or ""
                        )
                        == "passed"
                        and str(receipt.get("publication_status") or "")
                        == "published"
                    )
                )
            )
            authoritative_speech += int(speech_exact)
            formal_failed += int(
                str(receipt.get("classroom_status") or "") == "failed"
                if receipt is not None else False
            )
            formal_failed += int(
                str(audio.get("state") or "") in {"failed", "ambiguous"}
                if audio is not None else False
            )
        total = int(plan["total_course_count"])
        classroom_ready = int(classroom_ready_count)
        speech_ready = int(speech_ready_count)
        if not (
            total == 30
            and int(plan.get("content_candidate_count") or 0) == 30
            and int(plan.get("content_failed_count") or 0) == 0
            and int(plan.get("failed_course_count") or 0) == 0
            and formal_failed == 0
            and classroom_ready == authoritative_classrooms
            and speech_ready == authoritative_speech
            and 0 <= int(plan.get("classroom_ready_count") or 0)
            <= classroom_ready <= total
            and 0 <= int(plan.get("speech_ready_count") or 0)
            <= speech_ready <= classroom_ready
            and int(next_run_at) >= int(now)
        ):
            raise ValueError("formal preparation progress is invalid")
        if expected_stage == "building_classrooms":
            handoff = classroom_ready == total
            next_stage = "generating_speech" if handoff else expected_stage
            progress = 65 if handoff else min(
                64, 40 + classroom_ready * 24 // total
            )
        else:
            if classroom_ready != total:
                raise ValueError("speech stage requires all classrooms")
            handoff = speech_ready == total
            next_stage = "validating" if handoff else expected_stage
            progress = 85 if handoff else min(
                84, 65 + speech_ready * 19 // total
            )
        cursor = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET status = 'running', stage = ?, progress_percent = ?,
              classroom_ready_count = ?, speech_ready_count = ?,
              lease_token = NULL, lease_expires_at = NULL,
              heartbeat_at = NULL, hard_deadline_at = NULL,
              next_run_at = ?, resume_stage = NULL, work_unit_kind = NULL,
              bound_catalog_item_id = NULL,
              bound_content_attempt_ordinal = NULL,
              bound_content_phase = NULL, retry_reason_code = NULL,
              retry_message_safe = NULL, last_progress_at = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND stage = ?
              AND lease_token = ? AND target_fingerprint = ?
              AND lease_expires_at > ? AND hard_deadline_at > ?
            """,
            (
                next_stage, progress, classroom_ready, speech_ready,
                int(next_run_at), int(now), int(now), plan_id,
                expected_stage, lease_token, target_fingerprint,
                int(now), int(now),
            ),
        )
        if cursor.rowcount == 1:
            self.append_event(
                conn,
                plan_id=plan_id,
                event_type=(
                    "formal_stage_handoff" if handoff else "formal_stage_progress"
                ),
                stage=next_stage,
                payload={
                    "fromStage": expected_stage,
                    "toStage": next_stage,
                    "progressPercent": progress,
                },
                now=now,
            )
        return cursor.rowcount == 1, next_stage

    def persist_formal_validation_progress(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        lease_token: str,
        target_fingerprint: str,
        validation_ready_count: int,
        next_run_at: int,
        now: int,
    ) -> tuple[bool, str]:
        """Handoff only after every exact 057/058/059 receipt is terminal."""

        plan = self.get_plan(conn, plan_id, for_update=True)
        if not self._claim_matches(
            plan,
            lease_token=lease_token,
            target_fingerprint=target_fingerprint,
            expected_stage="validating",
            now=now,
        ):
            return False, "validating"
        assert plan is not None
        items = conn.execute(
            """
            SELECT item.id AS build_item_id,
              receipt.release_id AS receipt_release_id,
              receipt.grade_code AS receipt_grade_code,
              receipt.target_fingerprint AS receipt_target_fingerprint,
              receipt.runtime_classroom_id,
              receipt.classroom_status, receipt.tts_status,
              receipt.asr_roundtrip_status,
              receipt.conversation_provider_status,
              receipt.auto_validated, receipt.publication_status,
              audio.release_id AS audio_release_id,
              audio.grade_code AS audio_grade_code,
              audio.target_fingerprint AS audio_target_fingerprint,
              audio.runtime_classroom_id AS audio_runtime_classroom_id,
              audio.state AS audio_state,
              audio.classroom_content_sha256 AS audio_classroom_sha256,
              audio.terminal_receipt_hash AS audio_receipt_hash,
              provider.id AS provider_readiness_id,
              provider.build_item_id AS provider_build_item_id,
              provider.release_id AS provider_release_id,
              provider.grade_code AS provider_grade_code,
              provider.target_fingerprint AS provider_target_fingerprint,
              provider.runtime_classroom_id AS provider_runtime_classroom_id,
              provider.audio_job_terminal_receipt_hash,
              provider.route_session_provider_call,
              provider.route_session_status, provider.state AS provider_state,
              provider.expected_provider_call_count,
              provider.provider_attempted_count,
              provider.provider_passed_count,
              provider.provider_receipt_hash,
              (SELECT COUNT(*)
                 FROM learning_openmaic_provider_readiness_call_receipts AS call_row
                WHERE call_row.readiness_id = provider.id
                  AND call_row.state = 'passed'
                  AND call_row.provider_call = 1) AS passed_call_count
            FROM learning_catalog_build_items AS item
            JOIN learning_curriculum_classroom_item_receipts AS receipt
              ON receipt.build_item_id = item.id
            JOIN learning_formal_qwen_audio_jobs AS audio
              ON audio.build_item_id = item.id
            JOIN learning_openmaic_provider_readiness_jobs AS provider
              ON provider.release_id = item.release_id
             AND provider.grade_code = item.grade_code
             AND provider.target_fingerprint = receipt.target_fingerprint
            WHERE item.build_job_id = ? AND item.release_id = ?
            ORDER BY item.subject_ordinal, item.boundary_ordinal,
              item.variant_ordinal, item.id FOR UPDATE
            """,
            (plan["catalog_build_id"], plan["catalog_release_id"]),
        ).fetchall()
        witness = items[0] if items else {}
        provider_ids = {
            str(row.get("provider_readiness_id") or "")
            for row in items
            if str(row.get("provider_readiness_id") or "")
        }
        exact = [
            row
            for row in items
            if (
                str(row.get("receipt_release_id") or "")
                == str(plan["catalog_release_id"])
                and str(row.get("receipt_grade_code") or "")
                == str(plan["grade_code"])
                and str(row.get("receipt_target_fingerprint") or "")
                == target_fingerprint
                and str(row.get("classroom_status") or "") == "passed"
                and str(row.get("tts_status") or "") == "passed"
                and str(row.get("asr_roundtrip_status") or "") == "passed"
                and str(row.get("conversation_provider_status") or "")
                == "passed"
                and int(row.get("auto_validated") or 0) == 1
                and str(row.get("publication_status") or "")
                in {"pending", "published"}
                and str(row.get("audio_release_id") or "")
                == str(plan["catalog_release_id"])
                and str(row.get("audio_grade_code") or "")
                == str(plan["grade_code"])
                and str(row.get("audio_target_fingerprint") or "")
                == target_fingerprint
                and str(row.get("audio_runtime_classroom_id") or "")
                == str(row.get("runtime_classroom_id") or "")
                and str(row.get("audio_state") or "") == "auto_validated"
                and str(row.get("provider_release_id") or "")
                == str(plan["catalog_release_id"])
                and str(row.get("provider_grade_code") or "")
                == str(plan["grade_code"])
                and str(row.get("provider_target_fingerprint") or "")
                == target_fingerprint
                and len(provider_ids) == 1
                and str(row.get("provider_readiness_id") or "")
                == next(iter(provider_ids))
                and str(row.get("provider_build_item_id") or "")
                == str(witness.get("build_item_id") or "")
                and str(row.get("provider_runtime_classroom_id") or "")
                == str(witness.get("runtime_classroom_id") or "")
                and str(row.get("audio_job_terminal_receipt_hash") or "")
                == str(witness.get("audio_receipt_hash") or "")
                and int(row.get("route_session_provider_call") or 0) == 0
                and str(row.get("route_session_status") or "") == "passed"
                and str(row.get("provider_state") or "") == "auto_validated"
                and int(row.get("expected_provider_call_count") or 0) == 5
                and int(row.get("provider_attempted_count") or 0) == 5
                and int(row.get("provider_passed_count") or 0) == 5
                and int(row.get("passed_call_count") or 0) == 5
                and re.fullmatch(
                    r"[0-9a-f]{64}",
                    str(row.get("provider_receipt_hash") or ""),
                )
                is not None
            )
        ]
        terminal_invalid = any(
            str(row.get("provider_state") or "") in {"failed", "ambiguous"}
            or str(row.get("conversation_provider_status") or "") == "failed"
            for row in items
        )
        if not (
            len(items) == 30
            and len(exact) == int(validation_ready_count)
            and 0 <= int(validation_ready_count) <= 30
            and not terminal_invalid
            and int(plan.get("classroom_ready_count") or 0) == 30
            and int(plan.get("speech_ready_count") or 0) == 30
            and int(plan.get("validation_ready_count") or 0)
            <= int(validation_ready_count)
            and int(next_run_at) >= int(now)
        ):
            raise ValueError("formal validation readiness is incomplete")
        handoff = int(validation_ready_count) == 30
        next_stage = "publishing" if handoff else "validating"
        progress = (
            95
            if handoff
            else min(94, 85 + int(validation_ready_count) * 9 // 30)
        )
        updated = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET stage = ?, progress_percent = ?,
              validation_ready_count = ?, lease_token = NULL,
              lease_expires_at = NULL, heartbeat_at = NULL,
              hard_deadline_at = NULL, next_run_at = ?,
              work_unit_kind = NULL, last_progress_at = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND stage = 'validating'
              AND lease_token = ? AND target_fingerprint = ?
              AND lease_expires_at > ? AND hard_deadline_at > ?
            """,
            (
                next_stage,
                progress,
                int(validation_ready_count),
                int(next_run_at),
                int(now),
                int(now),
                plan_id,
                lease_token,
                target_fingerprint,
                int(now),
                int(now),
            ),
        )
        if updated.rowcount == 1:
            self.append_event(
                conn,
                plan_id=plan_id,
                event_type=(
                    "formal_stage_handoff"
                    if handoff
                    else "formal_stage_progress"
                ),
                stage=next_stage,
                payload={
                    "fromStage": "validating",
                    "toStage": next_stage,
                    "progressPercent": progress,
                    "validationReadyCount": int(validation_ready_count),
                },
                now=now,
            )
        return updated.rowcount == 1, (
            next_stage if updated.rowcount == 1 else "validating"
        )

    def start_formal_pipeline(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        target_fingerprint: str,
        now: int,
    ) -> bool:
        """Resume only the immutable 30/30 content handoff into Phase II."""

        plan = self.get_plan(conn, plan_id, for_update=True)
        if plan is None:
            return False
        try:
            is_v2 = self._is_v2_plan(plan)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return False
        if not (
            is_v2
            and str(plan.get("target_fingerprint") or "") == target_fingerprint
            and str(plan.get("status") or "") == "running"
            and str(plan.get("stage") or "") == "building_classrooms"
            and plan.get("catalog_build_id") is not None
            and plan.get("catalog_release_id") is not None
            and int(plan.get("content_target_count") or 0) == 30
            and int(plan.get("content_candidate_count") or 0) == 30
            and int(plan.get("content_failed_count") or 0) == 0
            and int(plan.get("content_canary_candidate_count") or 0) == 3
            and int(plan.get("content_canary_failed_count") or 0) == 0
            and plan.get("content_canary_passed_at") is not None
            and plan.get("content_generation_completed_at") is not None
            and int(plan.get("progress_percent") or 0) == 35
            and all(
                plan.get(field) is None
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
                )
            )
        ):
            return False
        updated = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET progress_percent = 40, next_run_at = ?,
              last_progress_at = ?, updated_at = ?
            WHERE id = ? AND target_fingerprint = ?
              AND status = 'running' AND stage = 'building_classrooms'
              AND progress_percent = 35 AND next_run_at IS NULL
              AND lease_token IS NULL AND hard_deadline_at IS NULL
            """,
            (int(now), int(now), int(now), plan_id, target_fingerprint),
        )
        if updated.rowcount == 1:
            self.append_event(
                conn,
                plan_id=plan_id,
                event_type="formal_pipeline_started",
                stage="building_classrooms",
                payload={"stage": "building_classrooms", "progressPercent": 40},
                now=now,
            )
        return updated.rowcount == 1

    def complete_formal_ready(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        lease_token: str,
        target_fingerprint: str,
        subject_progress: Mapping[str, Any],
        now: int,
    ) -> bool:
        """Complete V2 from locked pointer and receipt evidence only."""

        plan = self.get_plan(conn, plan_id, for_update=True)
        if not self._claim_matches(
            plan,
            lease_token=lease_token,
            target_fingerprint=target_fingerprint,
            expected_stage="publishing",
            now=now,
        ):
            return False
        if plan is None or not self._is_v2_plan(plan):
            return False
        total = int(plan["total_course_count"])
        self._validate_progress_counts(
            plan,
            ready_course_count=total,
            failed_course_count=0,
            subject_progress=subject_progress,
            monotonic=True,
        )
        pointer = conn.execute(
            """
            SELECT pointer.*, history.activation_source,
              history.publication_receipt_hash
            FROM learning_curriculum_grade_release_pointers AS pointer
            JOIN learning_curriculum_grade_release_history AS history
              ON history.id = pointer.history_id
            WHERE pointer.grade_code = ? AND pointer.pointer_revision >= 1
              AND pointer.release_id = ? AND pointer.target_fingerprint = ?
              AND history.superseded_at IS NULL
            LIMIT 1 FOR UPDATE
            """,
            (
                plan["grade_code"],
                plan["catalog_release_id"],
                target_fingerprint,
            ),
        ).fetchone()
        if not (
            pointer is not None
            and str(pointer.get("activation_source") or "")
            == "formal_publication"
            and str(pointer.get("contract_version") or "")
            == "mira.learning.formal-publication.v1"
            and re.fullmatch(
                r"[0-9a-f]{64}",
                str(pointer.get("publication_receipt_hash") or ""),
            )
            is not None
        ):
            return False
        evidence = conn.execute(
            """
            SELECT COUNT(*) AS receipt_count,
              SUM(
                receipt.grade_code = plan.grade_code
                AND receipt.release_id = plan.catalog_release_id
                AND receipt.target_fingerprint = plan.target_fingerprint
                AND receipt.binding_contract_version = ?
                AND receipt.publication_status = 'published'
                AND receipt.auto_validated = 1
                AND runtime.id IS NOT NULL
                AND runtime.candidate_build_item_id = item.id
                AND runtime.candidate_release_id = plan.catalog_release_id
                AND runtime.candidate_grade_code = plan.grade_code
                AND runtime.candidate_target_fingerprint = plan.target_fingerprint
                AND runtime.candidate_binding_contract_version = ?
                AND runtime.course_id = receipt.course_id
                AND runtime.course_version = receipt.course_version
                AND runtime.package_id = receipt.package_id
                AND runtime.package_version = receipt.package_version
                AND runtime.status = 'ready'
                AND audio.build_item_id = item.id
                AND audio.release_id = plan.catalog_release_id
                AND audio.grade_code = plan.grade_code
                AND audio.target_fingerprint = plan.target_fingerprint
                AND audio.runtime_classroom_id = runtime.id
                AND audio.course_id = receipt.course_id
                AND audio.course_version = receipt.course_version
                AND audio.package_id = receipt.package_id
                AND audio.package_version = receipt.package_version
                AND audio.state = 'auto_validated'
                AND audio.expected_segment_count BETWEEN 1 AND 240
                AND audio.tts_attempted_count = audio.expected_segment_count
                AND audio.tts_completed_count = audio.expected_segment_count
                AND audio.audio_validated_count = audio.expected_segment_count
                AND audio.asr_attempted_count = audio.expected_segment_count
                AND audio.asr_passed_count = audio.expected_segment_count
                AND provider.build_item_id = (
                  SELECT witness.id
                  FROM learning_catalog_build_items AS witness
                  WHERE witness.build_job_id = plan.catalog_build_id
                    AND witness.release_id = plan.catalog_release_id
                  ORDER BY witness.subject_ordinal,
                    witness.boundary_ordinal, witness.variant_ordinal,
                    witness.id
                  LIMIT 1
                )
                AND provider.release_id = plan.catalog_release_id
                AND provider.grade_code = plan.grade_code
                AND provider.target_fingerprint = plan.target_fingerprint
                AND provider.state = 'auto_validated'
                AND provider.expected_provider_call_count = 5
                AND provider.provider_attempted_count = 5
                AND provider.provider_passed_count = 5
                AND provider.provider_receipt_hash IS NOT NULL
                AND provider.route_session_provider_call = 0
                AND provider.route_session_status = 'passed'
                AND (SELECT COUNT(*)
                       FROM learning_openmaic_provider_readiness_call_receipts
                         AS provider_call
                      WHERE provider_call.readiness_id = provider.id
                        AND provider_call.state = 'passed'
                        AND provider_call.provider_call = 1) = 5
              ) AS exact_count
            FROM learning_curriculum_preparation_plans AS plan
            JOIN learning_catalog_build_items AS item
              ON item.build_job_id = plan.catalog_build_id
             AND item.release_id = plan.catalog_release_id
            LEFT JOIN learning_curriculum_classroom_item_receipts AS receipt
              ON receipt.build_item_id = item.id
            LEFT JOIN learning_openmaic_runtime_classrooms AS runtime
              ON runtime.id = receipt.runtime_classroom_id
            LEFT JOIN learning_formal_qwen_audio_jobs AS audio
              ON audio.build_item_id = item.id
            LEFT JOIN learning_openmaic_provider_readiness_jobs AS provider
              ON provider.release_id = plan.catalog_release_id
             AND provider.grade_code = plan.grade_code
             AND provider.target_fingerprint = plan.target_fingerprint
            WHERE plan.id = ?
            """,
            (
                self.CANDIDATE_BINDING_CONTRACT_VERSION,
                self.CANDIDATE_BINDING_CONTRACT_VERSION,
                plan_id,
            ),
        ).fetchone()
        if not (
            evidence is not None
            and int(evidence.get("receipt_count") or 0) == total
            and int(evidence.get("exact_count") or 0) == total
        ):
            return False
        updated = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET status = 'ready', stage = 'completed',
              ready_course_count = total_course_count, failed_course_count = 0,
              progress_percent = 100, subject_progress_json = ?,
              classroom_ready_count = total_course_count,
              speech_ready_count = total_course_count,
              validation_ready_count = total_course_count,
              published_course_count = total_course_count,
              formal_contract_version = ?,
              formal_publication_history_id = ?,
              formal_publication_receipt_hash = ?, formal_ready_at = ?,
              completed_at = ?, lease_token = NULL, lease_expires_at = NULL,
              heartbeat_at = NULL, next_run_at = NULL,
              hard_deadline_at = NULL, resume_stage = NULL,
              work_unit_kind = NULL, bound_catalog_item_id = NULL,
              bound_content_attempt_ordinal = NULL,
              bound_content_phase = NULL, retry_reason_code = NULL,
              retry_message_safe = NULL, error_code = NULL,
              error_message_safe = NULL, last_progress_at = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND stage = 'publishing'
              AND lease_token = ? AND target_fingerprint = ?
              AND lease_expires_at > ?
            """,
            (
                self._encode_json(subject_progress),
                pointer["contract_version"],
                pointer["history_id"],
                pointer["publication_receipt_hash"],
                int(now),
                int(now),
                int(now),
                int(now),
                plan_id,
                lease_token,
                target_fingerprint,
                int(now),
            ),
        )
        if updated.rowcount == 1:
            self.append_event(
                conn,
                plan_id=plan_id,
                event_type="formal_ready",
                stage="completed",
                payload={
                    "releaseId": str(plan["catalog_release_id"]),
                    "historyId": str(pointer["history_id"]),
                    "status": "ready",
                    "progressPercent": 100,
                },
                now=now,
            )
        return updated.rowcount == 1

    def complete_matching_formal_ready(
        self,
        conn: DatabaseConnection,
        *,
        publisher_plan_id: str,
        publisher_lease_token: str,
        grade_code: str,
        build_id: str,
        release_id: str,
        target_fingerprint: str,
        subject_progress: Mapping[str, Any],
        pointer: Mapping[str, Any],
        now: int,
    ) -> int:
        """Complete every current plan bound to the newly published grade."""

        plans = list(
            conn.execute(
                """
                SELECT * FROM learning_curriculum_preparation_plans
                WHERE grade_code = ? AND catalog_build_id = ?
                  AND catalog_release_id = ? AND target_fingerprint = ?
                  AND superseded_at IS NULL
                  AND status IN ('running', 'queued', 'ready')
                ORDER BY id FOR UPDATE
                """,
                (grade_code, build_id, release_id, target_fingerprint),
            ).fetchall()
        )
        publisher = next(
            (row for row in plans if str(row.get("id") or "") == publisher_plan_id),
            None,
        )
        if not (
            publisher is not None
            and str(publisher.get("status") or "") == "running"
            and str(publisher.get("stage") or "") == "publishing"
            and str(publisher.get("lease_token") or "")
            == publisher_lease_token
            and int(publisher.get("lease_expires_at") or 0) > int(now)
            and str(pointer.get("release_id") or "") == release_id
            and str(pointer.get("target_fingerprint") or "")
            == target_fingerprint
            and str(pointer.get("contract_version") or "")
            == self.FORMAL_PUBLICATION_CONTRACT_VERSION
            and re.fullmatch(
                r"[0-9a-f]{64}",
                str(pointer.get("publication_receipt_hash") or ""),
            )
            is not None
        ):
            return 0
        for plan in plans:
            if str(plan["id"]) == publisher_plan_id or str(
                plan.get("status") or ""
            ) == "ready":
                continue
            if plan.get("lease_token") is not None:
                raise ValueError(
                    "another formal preparation plan still owns an active lease"
                )
            if not (
                self._is_v2_plan(plan)
                and int(plan.get("total_course_count") or 0) == 30
                and int(plan.get("content_target_count") or 0) == 30
                and int(plan.get("content_candidate_count") or 0) == 30
                and int(plan.get("content_failed_count") or 0) == 0
                and int(plan.get("failed_course_count") or 0) == 0
            ):
                raise ValueError(
                    "matching formal preparation plan authority is incomplete"
                )
            self._validate_progress_counts(
                plan,
                ready_course_count=30,
                failed_course_count=0,
                subject_progress=subject_progress,
                monotonic=True,
            )
        if not self.complete_formal_ready(
            conn,
            plan_id=publisher_plan_id,
            lease_token=publisher_lease_token,
            target_fingerprint=target_fingerprint,
            subject_progress=subject_progress,
            now=now,
        ):
            return 0
        completed = 1
        for plan in plans:
            plan_id = str(plan["id"])
            if plan_id == publisher_plan_id:
                continue
            if str(plan.get("status") or "") == "ready":
                if not (
                    str(plan.get("stage") or "") == "completed"
                    and str(plan.get("formal_publication_history_id") or "")
                    == str(pointer.get("history_id") or "")
                    and str(plan.get("formal_publication_receipt_hash") or "")
                    == str(pointer.get("publication_receipt_hash") or "")
                ):
                    raise ValueError("formal ready plan replay conflict")
                completed += 1
                continue
            updated = conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET status = 'ready', stage = 'completed',
                  ready_course_count = total_course_count,
                  failed_course_count = 0, progress_percent = 100,
                  subject_progress_json = ?,
                  classroom_ready_count = total_course_count,
                  speech_ready_count = total_course_count,
                  validation_ready_count = total_course_count,
                  published_course_count = total_course_count,
                  formal_contract_version = ?,
                  formal_publication_history_id = ?,
                  formal_publication_receipt_hash = ?, formal_ready_at = ?,
                  completed_at = ?, lease_token = NULL,
                  lease_expires_at = NULL, heartbeat_at = NULL,
                  next_run_at = NULL, hard_deadline_at = NULL,
                  resume_stage = NULL, work_unit_kind = NULL,
                  bound_catalog_item_id = NULL,
                  bound_content_attempt_ordinal = NULL,
                  bound_content_phase = NULL, retry_reason_code = NULL,
                  retry_message_safe = NULL, error_code = NULL,
                  error_message_safe = NULL, last_progress_at = ?, updated_at = ?
                WHERE id = ? AND superseded_at IS NULL
                  AND status IN ('running', 'queued') AND lease_token IS NULL
                  AND catalog_build_id = ? AND catalog_release_id = ?
                  AND target_fingerprint = ?
                """,
                (
                    self._encode_json(subject_progress),
                    pointer["contract_version"],
                    pointer["history_id"],
                    pointer["publication_receipt_hash"],
                    int(now),
                    int(now),
                    int(now),
                    int(now),
                    plan_id,
                    build_id,
                    release_id,
                    target_fingerprint,
                ),
            )
            if updated.rowcount != 1:
                raise ValueError(
                    "matching formal preparation plan changed during publication"
                )
            self.append_event(
                conn,
                plan_id=plan_id,
                event_type="formal_ready",
                stage="completed",
                payload={
                    "releaseId": release_id,
                    "historyId": str(pointer["history_id"]),
                    "status": "ready",
                    "progressPercent": 100,
                },
                now=now,
            )
            completed += 1
        return completed

    def bind_shared_build(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        lease_token: str,
        catalog_build_id: str,
        catalog_release_id: str,
        now: int,
    ) -> bool:
        cursor = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET catalog_build_id = ?, catalog_release_id = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND lease_token = ?
              AND stage IN ('queued', 'planning')
              AND (catalog_build_id IS NULL OR catalog_build_id = ?)
              AND (catalog_release_id IS NULL OR catalog_release_id = ?)
            """,
            (
                catalog_build_id,
                catalog_release_id,
                int(now),
                plan_id,
                lease_token,
                catalog_build_id,
                catalog_release_id,
            ),
        )
        return cursor.rowcount == 1

    def mark_retry_wait(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        lease_token: str,
        expected_stage: str,
        next_run_at: int,
        now: int,
    ) -> bool:
        if expected_stage not in self.WORK_STAGES:
            return False
        cursor = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET status = 'queued', stage = 'retry_wait', resume_stage = ?,
              lease_token = NULL, lease_expires_at = NULL, heartbeat_at = NULL,
              next_run_at = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND stage = ?
              AND lease_token = ?
            """,
            (
                expected_stage,
                int(next_run_at),
                int(now),
                plan_id,
                expected_stage,
                lease_token,
            ),
        )
        return cursor.rowcount == 1

    def mark_failed(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        lease_token: str,
        expected_stage: str,
        error_code: str,
        error_message: object,
        ready_course_count: int,
        failed_course_count: int,
        subject_progress: Mapping[str, Any],
        now: int,
    ) -> bool:
        if expected_stage not in self.CLAIMABLE_STAGES:
            return False
        plan = self.get_plan(conn, plan_id)
        if plan is None:
            return False
        self._validate_progress_counts(
            plan,
            ready_course_count=ready_course_count,
            failed_course_count=failed_course_count,
            subject_progress=subject_progress,
            monotonic=True,
        )
        safe_code = self._safe_code(error_code)
        safe_message = DynamicLearningCourseRepository.sanitize_error(error_message)
        progress = self._progress_percent(
            expected_stage,
            ready_course_count=int(ready_course_count),
            failed_course_count=int(failed_course_count),
            total_course_count=int(plan["total_course_count"]),
            previous=int(plan["progress_percent"]),
        )
        cursor = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET status = 'failed', stage = 'completed',
              ready_course_count = ?, failed_course_count = ?,
              progress_percent = ?, subject_progress_json = ?,
              error_code = ?, error_message_safe = ?, completed_at = ?,
              lease_token = NULL, lease_expires_at = NULL, heartbeat_at = NULL,
              next_run_at = NULL, hard_deadline_at = NULL, resume_stage = NULL,
              work_unit_kind = NULL, bound_catalog_item_id = NULL,
              bound_content_attempt_ordinal = NULL, bound_content_phase = NULL,
              retry_reason_code = NULL, retry_message_safe = NULL,
              last_progress_at = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND stage = ?
              AND lease_token = ?
            """,
            (
                int(ready_course_count),
                int(failed_course_count),
                progress,
                self._encode_json(subject_progress),
                safe_code,
                safe_message,
                int(now),
                int(now),
                int(now),
                plan_id,
                expected_stage,
                lease_token,
            ),
        )
        return cursor.rowcount == 1

    def mark_ready(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        lease_token: str,
        expected_stage: str,
        ready_course_count: int,
        subject_progress: Mapping[str, Any],
        now: int,
    ) -> bool:
        if expected_stage != "publishing":
            return False
        plan = self.get_plan(conn, plan_id)
        if (
            plan is None
            or self._is_v2_plan(plan)
            or int(ready_course_count) != int(plan["total_course_count"])
        ):
            return False
        self._validate_progress_counts(
            plan,
            ready_course_count=ready_course_count,
            failed_course_count=0,
            subject_progress=subject_progress,
            monotonic=True,
        )
        cursor = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET status = 'ready', stage = 'completed', ready_course_count = ?,
              failed_course_count = 0, progress_percent = 100,
              subject_progress_json = ?, error_code = NULL,
              error_message_safe = NULL, completed_at = ?,
              lease_token = NULL, lease_expires_at = NULL, heartbeat_at = NULL,
              next_run_at = NULL, hard_deadline_at = NULL, resume_stage = NULL,
              last_progress_at = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND stage = ?
              AND lease_token = ?
            """,
            (
                int(ready_course_count),
                self._encode_json(subject_progress),
                int(now),
                int(now),
                int(now),
                plan_id,
                expected_stage,
                lease_token,
            ),
        )
        return cursor.rowcount == 1

    def release_lease(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        lease_token: str,
        expected_stage: str,
        now: int,
    ) -> bool:
        if expected_stage == "queued":
            stage = "queued"
            resume_stage = None
        elif expected_stage in self.WORK_STAGES:
            stage = "retry_wait"
            resume_stage = expected_stage
        else:
            return False
        cursor = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET status = 'queued', stage = ?, resume_stage = ?,
              lease_token = NULL, lease_expires_at = NULL, heartbeat_at = NULL,
              retry_reason_code = CASE WHEN ? = 'retry_wait'
                THEN COALESCE(retry_reason_code, 'preparation_dependency_unavailable')
                ELSE NULL END,
              retry_message_safe = CASE WHEN ? = 'retry_wait'
                THEN COALESCE(retry_message_safe, ?) ELSE NULL END,
              next_run_at = LEAST(?, COALESCE(hard_deadline_at, ?)), updated_at = ?
            WHERE id = ? AND status = 'running' AND stage = ?
              AND lease_token = ?
            """,
            (
                stage,
                resume_stage,
                stage,
                stage,
                self.PUBLIC_FAILURES['preparation_dependency_unavailable'],
                int(now),
                int(now),
                int(now),
                plan_id,
                expected_stage,
                lease_token,
            ),
        )
        return cursor.rowcount == 1

    def append_event(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        event_type: str,
        stage: str,
        payload: Mapping[str, Any],
        now: int,
    ) -> DatabaseRow:
        if self._SAFE_EVENT_TYPE.fullmatch(str(event_type or "")) is None:
            raise ValueError("preparation event type must be a safe bounded code")
        if stage not in (*self.CLAIMABLE_STAGES, "retry_wait", "completed"):
            raise ValueError("unsupported preparation event stage")
        safe_payload = self._validate_event_payload(payload)
        payload_json = self._encode_json(safe_payload, sort_keys=True)
        identity = f"{plan_id}:{event_type}:{stage}:{int(now)}:{payload_json}"
        event_id = self._stable_id("learning_prep_event", identity)
        conn.execute(
            """
            INSERT INTO learning_curriculum_preparation_events(
              id, plan_id, event_type, stage, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE id = id
            """,
            (event_id, plan_id, event_type, stage, payload_json, int(now)),
        )
        row = conn.execute(
            """
            SELECT * FROM learning_curriculum_preparation_events
            WHERE id = ? LIMIT 1
            """,
            (event_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("learning curriculum preparation event was not persisted")
        return row

    def _lock_shared_authority(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        catalog_build_id: str,
        catalog_release_id: str | None = None,
        catalog_item_id: str | None = None,
        lock_all_items: bool = False,
        reject_dispatch_identity: tuple[int, str] | None = None,
        provider_dependency_identity: tuple[int, str] | None = None,
        host_dependency_identity: tuple[int, str] | None = None,
        dependency_authority_out: list[object] | None = None,
    ) -> tuple[
        DatabaseRow,
        DatabaseRow,
        list[DatabaseRow],
        DatabaseRow,
        DatabaseRow,
    ] | None:
        if dependency_authority_out is not None:
            dependency_authority_out[:] = []
        hint = self.get_plan(conn, plan_id)
        if hint is None:
            return None
        release_id = str(
            catalog_release_id or hint.get("catalog_release_id") or ""
        )
        if not release_id:
            build_hint = conn.execute(
                "SELECT release_id FROM learning_catalog_build_jobs "
                "WHERE id = ? LIMIT 1",
                (catalog_build_id,),
            ).fetchone()
            release_id = str(
                build_hint.get("release_id") if build_hint is not None else ""
            )
        if not release_id:
            return None
        release = conn.execute(
            "SELECT * FROM learning_catalog_releases "
            "WHERE id = ? LIMIT 1 FOR UPDATE",
            (release_id,),
        ).fetchone()
        build = conn.execute(
            "SELECT * FROM learning_catalog_build_jobs "
            "WHERE id = ? AND release_id = ? LIMIT 1 FOR UPDATE",
            (catalog_build_id, release_id),
        ).fetchone()
        if release is None or build is None:
            return None
        if lock_all_items:
            items = list(
                conn.execute(
                    """
                    SELECT * FROM learning_catalog_build_items
                    WHERE build_job_id = ?
                    ORDER BY subject_ordinal, boundary_ordinal,
                      variant_ordinal, id
                    FOR UPDATE
                    """,
                    (catalog_build_id,),
                ).fetchall()
            )
        elif catalog_item_id is not None:
            item = conn.execute(
                """
                SELECT * FROM learning_catalog_build_items
                WHERE id = ? AND build_job_id = ? LIMIT 1 FOR UPDATE
                """,
                (catalog_item_id, catalog_build_id),
            ).fetchone()
            if item is None:
                return None
            items = [item]
        else:
            items = []
        release_item = conn.execute(
            """
            SELECT release_id, status, quality_status, retired_at
            FROM learning_catalog_release_items
            WHERE release_id = ? LIMIT 1 FOR UPDATE
            """,
            (release_id,),
        ).fetchone()
        expected_published = int(release.get("ready_item_count") or 0)
        hinted_published = int(hint.get("published_course_count") or 0)
        if release_item is None:
            if expected_published != 0 or hinted_published != 0:
                return None
        else:
            if (
                expected_published < 1
                or expected_published != hinted_published
                or str(release_item.get("status") or "") != "published"
                or str(release_item.get("quality_status") or "") != "ready"
                or release_item.get("retired_at") is not None
            ):
                return None
            release_items = list(
                conn.execute(
                    """
                    SELECT release_id, status, quality_status, retired_at
                    FROM learning_catalog_release_items
                    WHERE release_id = ?
                    ORDER BY subject, skill_id, variant_ordinal, course_id
                    FOR UPDATE
                    """,
                    (release_id,),
                ).fetchall()
            )
            if (
                len(release_items) != expected_published
                or any(
                    str(item.get("release_id") or "") != release_id
                    or str(item.get("status") or "") != "published"
                    or str(item.get("quality_status") or "") != "ready"
                    or item.get("retired_at") is not None
                    for item in release_items
                )
            ):
                return None
        if provider_dependency_identity is not None:
            if catalog_item_id is None or len(items) != 1:
                return None
            logical_attempt, content_phase = provider_dependency_identity
            if (
                type(logical_attempt) is not int
                or logical_attempt not in {1, 2}
                or not isinstance(content_phase, str)
                or not content_phase
            ):
                return None
            item_dispatches = list(
                conn.execute(
                    """
                    SELECT * FROM learning_course_provider_dispatches
                    WHERE build_item_id = ? AND logical_attempt IN (1, 2)
                    ORDER BY logical_attempt, phase_ordinal, id
                    FOR UPDATE
                    """,
                    (catalog_item_id,),
                ).fetchall()
            )
            histories = self._load_parent_retry_attempt_histories(
                conn,
                items=items,
                dispatches=item_dispatches,
                lock=True,
            )
            try:
                historical_fingerprints = (
                    historical_question_fingerprint_snapshots(
                        conn,
                        item=items[0],
                        histories=histories.get(catalog_item_id, {}),
                    )
                )
            except ValueError:
                return None
            auditor = self.content_provider_dependency_auditor
            if auditor is None:
                return None
            try:
                sealed_provider = auditor(
                    evidence={
                        "item": dict(items[0]),
                        "attemptHistories": histories.get(catalog_item_id, {}),
                        "historicalQuestionFingerprintsByAttempt": (
                            historical_fingerprints
                        ),
                    },
                    content_phase=content_phase,
                )
            except Exception:
                return None
            if not (
                isinstance(
                    sealed_provider, ContentProviderDependencyAuditSnapshot
                )
                and sealed_provider.build_id == catalog_build_id
                and sealed_provider.release_id == release_id
                and sealed_provider.item_id == catalog_item_id
                and sealed_provider.logical_attempt == logical_attempt
                and sealed_provider.content_phase == content_phase
            ):
                return None
            if dependency_authority_out is not None:
                dependency_authority_out.append(sealed_provider)
        if host_dependency_identity is not None:
            if catalog_item_id is None or len(items) != 1:
                return None
            logical_attempt, content_phase = host_dependency_identity
            if (
                type(logical_attempt) is not int
                or logical_attempt not in {1, 2}
                or content_phase != "host_gate_running"
            ):
                return None
            item_dispatches = list(
                conn.execute(
                    """
                    SELECT * FROM learning_course_provider_dispatches
                    WHERE build_item_id = ? AND logical_attempt IN (1, 2)
                    ORDER BY logical_attempt, phase_ordinal, id
                    FOR UPDATE
                    """,
                    (catalog_item_id,),
                ).fetchall()
            )
            histories = self._load_parent_retry_attempt_histories(
                conn,
                items=items,
                dispatches=item_dispatches,
                lock=True,
            )
            try:
                historical_fingerprints = (
                    historical_question_fingerprint_snapshots(
                        conn,
                        item=items[0],
                        histories=histories.get(catalog_item_id, {}),
                    )
                )
            except ValueError:
                return None
            auditor = self.content_host_dependency_auditor
            if auditor is None:
                return None
            try:
                sealed_host = auditor(
                    evidence={
                        "item": dict(items[0]),
                        "attemptHistories": histories.get(catalog_item_id, {}),
                        "historicalQuestionFingerprintsByAttempt": (
                            historical_fingerprints
                        ),
                    }
                )
            except Exception:
                return None
            if not (
                isinstance(sealed_host, ContentHostDependencyAuditSnapshot)
                and sealed_host.build_id == catalog_build_id
                and sealed_host.release_id == release_id
                and sealed_host.item_id == catalog_item_id
                and sealed_host.logical_attempt == logical_attempt
                and sealed_host.content_phase == content_phase
            ):
                return None
            if dependency_authority_out is not None:
                dependency_authority_out.append(sealed_host)
        if reject_dispatch_identity is not None:
            if catalog_item_id is None:
                return None
            logical_attempt, content_phase = reject_dispatch_identity
            if (
                type(logical_attempt) is not int
                or logical_attempt not in {1, 2}
                or not isinstance(content_phase, str)
                or not content_phase
            ):
                return None
            target_dispatch = conn.execute(
                """
                SELECT id FROM learning_course_provider_dispatches
                WHERE build_item_id = ? AND logical_attempt = ?
                  AND phase = ? LIMIT 1 FOR UPDATE
                """,
                (catalog_item_id, logical_attempt, content_phase),
            ).fetchone()
            if target_dispatch is not None:
                return None
        child = conn.execute(
            """
            SELECT * FROM children
            WHERE id = ? AND family_id = ? LIMIT 1 FOR UPDATE
            """,
            (hint["child_id"], hint["family_id"]),
        ).fetchone()
        plan = self.get_plan(conn, plan_id, for_update=True)
        if plan is None or not self._plan_owner_matches(plan, child):
            return None
        return release, build, items, child, plan

    @staticmethod
    def _plan_owner_matches(plan, child) -> bool:
        library_key = plan.get("library_target_fingerprint")
        if library_key is not None:
            return bool(
                library_key == plan.get("target_fingerprint")
                and plan.get("family_id") is None
                and plan.get("child_id") is None
                and plan.get("grade_selection_revision") == 0
            )
        return bool(
            child is not None
            and child.get("id") == plan.get("child_id")
            and child.get("family_id") == plan.get("family_id")
            and child.get("grade_code") == plan.get("grade_code")
            and child.get("grade_selection_revision") == plan.get("grade_selection_revision")
        )

    @classmethod
    def _shared_authority_matches(
        cls,
        *,
        release: Mapping[str, object],
        build: Mapping[str, object],
        items: Sequence[Mapping[str, object]] | None,
        child: Mapping[str, object],
        plan: Mapping[str, object],
        target_fingerprint: str,
        allow_unbound_plan_catalog_ids: bool = False,
    ) -> bool:
        try:
            target = json.loads(str(plan["target_spec_json"]))
            build_target = json.loads(str(build["target_spec_json"]))
            canonical_target = cls._encode_json(target, sort_keys=True)
            canonical_build_target = cls._encode_json(
                build_target, sort_keys=True
            )
            canary_json = cls._encode_json(
                target["canaryManifest"], sort_keys=True
            )
            request_id = str(build["request_id"])
            request_digest = hashlib.sha256(
                request_id.encode("utf-8")
            ).hexdigest()[:24]
            expected_build_id = f"catalog_build_{request_digest}"
            expected_release_id = f"catalog_release_{request_digest}"
            plan_build_id = plan.get("catalog_build_id")
            plan_release_id = plan.get("catalog_release_id")
            plan_catalog_pair_matches = bool(
                (
                    allow_unbound_plan_catalog_ids
                    and plan_build_id is None
                    and plan_release_id is None
                )
                or (
                    str(plan_build_id or "") == expected_build_id
                    and str(plan_release_id or "") == expected_release_id
                )
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return False
        if not (
            str(target.get("schemaVersion") or "") == TARGET_SCHEMA_V2
            and str(target.get("gradeCode") or "") == "primary_1"
            and compatible_preparation_target(
                target, build_preparation_target("primary_1")
            )
            and preparation_target_fingerprint(target) == target_fingerprint
            and str(build.get("request_id") or "")
            == f"grade-build:{target_fingerprint}"
            and str(build.get("id") or "") == expected_build_id
            and str(build.get("release_id") or "") == expected_release_id
            and str(release.get("id") or "") == expected_release_id
            and str(plan.get("target_fingerprint") or "")
            == target_fingerprint
            and canonical_target == canonical_build_target
            and str(build.get("execution_mode") or "") == "content_only"
            and str(build.get("stage_ceiling") or "") == "content_ready"
            and str(build.get("content_manifest_version") or "")
            == str(target["schemaVersion"])
            and str(build.get("curriculum_version") or "")
            == str(target["curriculumVersion"])
            and str(build.get("canary_manifest_json") or "") == canary_json
            and type(build.get("total_item_count")) is int
            and int(build["total_item_count"]) == 30
            and type(build.get("ready_item_count")) is int
            and int(build["ready_item_count"]) == 0
            and type(build.get("failed_item_count")) is int
            and int(build["failed_item_count"]) == 0
            and str(build.get("request_id") or "")
            == str(plan.get("shared_build_request_id") or "")
            and str(build.get("release_id") or "")
            == str(release.get("id") or "")
            and plan_catalog_pair_matches
            and str(release.get("status") or "") == "draft"
            and str(release.get("quality_status") or "") == "building"
            and str(release.get("curriculum_version") or "")
            == str(plan.get("curriculum_version") or "")
            and str(plan.get("curriculum_version") or "")
            == str(target["curriculumVersion"])
            and str(plan.get("preparation_contract_version") or "")
            == str(target["preparationContractVersion"])
            and str(plan.get("grade_code") or "")
            == str(target["gradeCode"])
            and type(release.get("required_boundary_count")) is int
            and int(release["required_boundary_count"]) == 10
            and type(release.get("ready_item_count")) is int
            and 0 <= int(release["ready_item_count"]) <= 30
            and int(release["ready_item_count"])
            == int(plan.get("published_course_count") or 0)
            and int(plan.get("published_course_count") or 0)
            <= int(plan.get("validation_ready_count") or 0)
            <= int(plan.get("speech_ready_count") or 0)
            <= int(plan.get("classroom_ready_count") or 0)
            <= int(plan.get("total_course_count") or 0)
            and release.get("activated_at") is None
            and release.get("retired_at") is None
            and cls._plan_owner_matches(plan, child)
            and str(build.get("status") or "") in {"queued", "running"}
            and build.get("error_code") is None
            and build.get("error_message_safe") is None
            and build.get("completed_at") is None
        ):
            return False
        if items is None:
            return True
        return len(items) == 30 and all(
            cls._canonical_content_item_identity_matches(
                release=release,
                build=build,
                item=item,
                target=target,
            )
            for item in items
        )

    @classmethod
    def _canonical_content_item_identity_matches(
        cls,
        *,
        release: Mapping[str, object],
        build: Mapping[str, object],
        item: Mapping[str, object],
        target: Mapping[str, object] | None = None,
    ) -> bool:
        if any(
            type(item.get(field)) is not int
            for field in (
                "subject_ordinal",
                "boundary_ordinal",
                "variant_ordinal",
                "package_attempt_count",
            )
        ):
            return False
        try:
            decoded_target = (
                dict(target)
                if isinstance(target, Mapping)
                else json.loads(str(build["target_spec_json"]))
            )
            course_targets = decoded_target["courseTargets"]
            if not isinstance(course_targets, Sequence):
                return False
            identity_target = next(
                value
                for value in course_targets
                if isinstance(value, Mapping)
                and type(value.get("subjectOrdinal")) is int
                and type(value.get("boundaryOrdinal")) is int
                and type(value.get("variantOrdinal")) is int
                and int(value["subjectOrdinal"])
                == int(item["subject_ordinal"])
                and int(value["boundaryOrdinal"])
                == int(item["boundary_ordinal"])
                and int(value["variantOrdinal"])
                == int(item["variant_ordinal"])
            )
            subject = str(identity_target["subject"])
            skill_id = str(identity_target["skillId"])
            variant = int(identity_target["variantOrdinal"])
            identity = (
                f"{build['id']}:primary_1:{subject}:{skill_id}:{variant}"
            )
            item_digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError):
            return False
        return bool(
            str(item.get("id") or "")
            == f"catalog_build_item_{item_digest[:24]}"
            and str(item.get("generation_request_id") or "")
            == f"catalog_gen_{item_digest[:48]}"
            and str(item.get("build_job_id") or "")
            == str(build.get("id") or "")
            and str(item.get("release_id") or "")
            == str(release.get("id") or "")
            and str(item.get("grade_code") or "") == "primary_1"
            and str(item.get("execution_mode_snapshot") or "")
            == "content_only"
            and str(item.get("content_manifest_version_snapshot") or "")
            == str(decoded_target.get("schemaVersion") or "")
            and str(item.get("curriculum_version") or "")
            == str(decoded_target.get("curriculumVersion") or "")
            and str(item.get("subject") or "") == subject
            and str(item.get("skill_id") or "") == skill_id
            and str(item.get("boundary_version") or "")
            == str(identity_target.get("boundaryVersion") or "")
            and int(item["package_attempt_count"]) == 0
            and item.get("active_package_request_id") is None
            and item.get("package_id") is None
            and item.get("package_version") is None
        )

    @staticmethod
    def _active_content_build_matches(
        build: Mapping[str, object], *, require_running: bool
    ) -> bool:
        expected_statuses = {"running"} if require_running else {"queued", "running"}
        return bool(
            str(build.get("status") or "") in expected_statuses
            and build.get("error_code") is None
            and build.get("error_message_safe") is None
            and build.get("completed_at") is None
        )

    @classmethod
    def _content_work_item_authority_matches(
        cls,
        *,
        release: Mapping[str, object],
        build: Mapping[str, object],
        item: Mapping[str, object],
        logical_attempt: int,
        content_phase: str,
        content_lease_token: str,
        item_work_unit_deadline_at: int,
        now: int,
    ) -> bool:
        exact_int_fields = (
            "attempt_count",
            "content_claim_attempt_ordinal",
            "content_attempt_started_at",
            "content_lease_expires_at",
            "content_work_unit_deadline_at",
            "content_gate_attempt_count",
            "subject_ordinal",
            "boundary_ordinal",
            "variant_ordinal",
        )
        if any(type(item.get(field)) is not int for field in exact_int_fields):
            return False
        if not cls._canonical_content_item_identity_matches(
            release=release,
            build=build,
            item=item,
        ):
            return False
        request_id = str(item.get("generation_request_id") or "")
        expected_active_request = request_id + (
            ".attempt2" if logical_attempt == 2 else ""
        )
        attempt_started_at = int(item["content_attempt_started_at"])
        work_deadline_at = int(item["content_work_unit_deadline_at"])
        if not (
            cls._active_content_build_matches(build, require_running=True)
            and str(item.get("build_job_id") or "")
            == str(build.get("id") or "")
            and str(item.get("release_id") or "")
            == str(release.get("id") or "")
            and str(item.get("grade_code") or "") == "primary_1"
            and str(item.get("execution_mode_snapshot") or "")
            == "content_only"
            and str(item.get("content_manifest_version_snapshot") or "")
            == TARGET_SCHEMA_V2
            and str(item.get("status") or "") == "processing"
            and int(item["attempt_count"]) == logical_attempt
            and int(item["content_claim_attempt_ordinal"])
            == logical_attempt
            and str(item.get("claim_origin_status") or "")
            == ("failed" if logical_attempt == 2 else "pending")
            and bool(request_id)
            and str(item.get("active_generation_request_id") or "")
            == expected_active_request
            and str(item.get("content_phase") or "") == content_phase
            and str(item.get("content_lease_token") or "")
            == content_lease_token
            and int(item["content_lease_expires_at"])
            == item_work_unit_deadline_at
            and work_deadline_at == item_work_unit_deadline_at
            and item_work_unit_deadline_at > int(now)
            and attempt_started_at > 0
            and item.get("content_gate_passed_at") is None
        ):
            return False
        kind = cls._work_unit_kind(content_phase)
        if kind == "provider_phase":
            outer = item.get("content_provider_attempt_hard_deadline_at")
            return bool(
                type(outer) is int
                and provider_attempt_deadline_is_valid(
                    attempt_started_at, outer
                )
                and int(outer) > int(now)
                and work_deadline_at <= int(outer)
                and str(item.get("content_gate_status") or "")
                == "not_started"
                and int(item["content_gate_attempt_count"]) == 0
            )
        return bool(
            item.get("content_provider_attempt_hard_deadline_at") is None
            and str(item.get("content_gate_status") or "")
            in {"pending", "retry_wait"}
            and 1 <= int(item["content_gate_attempt_count"]) <= 3
        )

    @classmethod
    def _validate_content_binding_inputs(cls, **values: object) -> None:
        for field in (
            "plan_id",
            "plan_lease_token",
            "catalog_build_id",
            "catalog_item_id",
            "content_lease_token",
            "content_phase",
        ):
            cls._validate_identifier(values[field], field)
        fingerprint = values["target_fingerprint"]
        if not isinstance(fingerprint, str) or re.fullmatch(
            r"[0-9a-f]{64}", fingerprint
        ) is None:
            raise ValueError("target_fingerprint must be canonical SHA-256")
        attempt = values["logical_attempt"]
        if type(attempt) is not int or attempt not in (1, 2):
            raise ValueError("logical_attempt must be one or two")
        cls._require_timestamp(
            values["item_work_unit_deadline_at"],
            "item_work_unit_deadline_at",
        )
        cls._require_timestamp(values["now"], "now")
        cls._work_unit_kind(str(values["content_phase"]))

    @staticmethod
    def _work_unit_kind(content_phase: str) -> str:
        if content_phase == "host_gate_running":
            return "host_gate"
        if content_phase not in _CONTENT_PROVIDER_PHASES:
            raise ValueError("content phase is not a bindable work unit")
        return "provider_phase"

    @classmethod
    def _dependency_retry_binding_matches(
        cls,
        *,
        release: Mapping[str, object],
        build: Mapping[str, object],
        plan: Mapping[str, object],
        items: Sequence[Mapping[str, object]],
        now: int,
        sealed_retry_authority: object | None,
        bound_content_lease_token: str | None,
        bound_item_work_unit_deadline_at: int | None,
    ) -> bool:
        kind = str(plan.get("work_unit_kind") or "")
        if kind == "coordinator":
            return bool(
                not items
                and plan.get("bound_catalog_item_id") is None
                and plan.get("bound_content_attempt_ordinal") is None
                and plan.get("bound_content_phase") is None
                and isinstance(
                    sealed_retry_authority, ParentRetryAuthoritySnapshot
                )
                and sealed_retry_authority.authority_class
                == "pre_provider_dependency"
                and sealed_retry_authority.provider_dispatch_count == 0
                and sealed_retry_authority.open_or_ambiguous_dispatch_count == 0
                and sealed_retry_authority.failed_safe_dispatch_count == 0
                and not sealed_retry_authority.provider_graph_complete
                and sealed_retry_authority.next_work_kind is None
                and sealed_retry_authority.build_error_code is None
            )
        if len(items) != 1:
            return False
        item = items[0]
        phase = str(plan.get("bound_content_phase") or "")
        try:
            expected_kind = cls._work_unit_kind(phase)
        except ValueError:
            return False
        attempt = plan.get("bound_content_attempt_ordinal")
        deadline = plan.get("hard_deadline_at")
        if (
            expected_kind != kind
            or type(attempt) is not int
            or attempt not in {1, 2}
            or type(deadline) is not int
            or int(deadline) <= int(now)
            or not isinstance(bound_content_lease_token, str)
            or not bound_content_lease_token
            or type(bound_item_work_unit_deadline_at) is not int
            or int(bound_item_work_unit_deadline_at) != int(deadline)
            or not cls._canonical_content_item_identity_matches(
                release=release,
                build=build,
                item=item,
            )
        ):
            return False
        request_id = str(item.get("generation_request_id") or "")
        expected_request = request_id + (".attempt2" if attempt == 2 else "")
        exact_int_fields = (
            "attempt_count",
            "content_claim_attempt_ordinal",
            "content_gate_attempt_count",
            "content_attempt_started_at",
        )
        if not (
            all(type(item.get(field)) is int for field in exact_int_fields)
            and str(item.get("id") or "")
            == str(plan.get("bound_catalog_item_id") or "")
            and str(item.get("status") or "") == "processing"
            and int(item["attempt_count"]) == int(attempt)
            and int(item["content_claim_attempt_ordinal"]) == int(attempt)
            and bool(request_id)
            and str(item.get("active_generation_request_id") or "")
            == expected_request
            and str(item.get("content_phase") or "") == phase
            and int(item.get("content_work_unit_deadline_at") or 0)
            == int(deadline)
            and item.get("content_gate_passed_at") is None
            and item.get("content_validation_contract_version") is None
            and item.get("content_receipt_hash") is None
        ):
            return False
        attempt_started = int(item["content_attempt_started_at"])
        if kind == "provider_phase":
            outer = item.get("content_provider_attempt_hard_deadline_at")
            return bool(
                sealed_retry_authority is None
                and item.get("content_lease_token") is None
                and item.get("content_lease_expires_at") is None
                and item.get("content_heartbeat_at") is None
                and type(item.get("content_work_unit_deadline_at")) is int
                and int(item["content_work_unit_deadline_at"]) > int(now)
                and attempt_started > 0
                and type(outer) is int
                and provider_attempt_deadline_is_valid(
                    attempt_started, outer
                )
                and int(outer) > int(now)
                and int(item["content_work_unit_deadline_at"]) <= int(outer)
                and str(item.get("content_gate_status") or "")
                == "not_started"
                and int(item["content_gate_attempt_count"]) == 0
            )
        token = item.get("content_lease_token")
        lease = item.get("content_lease_expires_at")
        heartbeat = item.get("content_heartbeat_at")
        work_deadline = item.get("content_work_unit_deadline_at")
        return bool(
            isinstance(
                sealed_retry_authority,
                ContentHostDependencyAuditSnapshot,
            )
            and sealed_retry_authority.build_id
            == str(build.get("id") or "")
            and sealed_retry_authority.release_id
            == str(release.get("id") or "")
            and sealed_retry_authority.item_id
            == str(item.get("id") or "")
            and sealed_retry_authority.logical_attempt == attempt
            and sealed_retry_authority.content_phase == phase
            and phase == "host_gate_running"
            and str(item.get("content_gate_status") or "") == "retry_wait"
            and 1 <= int(item["content_gate_attempt_count"]) <= 3
            and item.get("content_provider_attempt_hard_deadline_at") is None
            and isinstance(token, str)
            and token == bound_content_lease_token
            and type(lease) is int
            and type(heartbeat) is int
            and type(work_deadline) is int
            and int(lease) == int(work_deadline) == int(deadline)
            and 0 <= int(heartbeat) < int(deadline)
        )

    @staticmethod
    def _coordinator_dependency_item_is_pristine(
        item: Mapping[str, object],
    ) -> bool:
        return bool(
            type(item.get("attempt_count")) is int
            and int(item["attempt_count"]) == 0
            and type(item.get("package_attempt_count")) is int
            and int(item["package_attempt_count"]) == 0
            and type(item.get("content_gate_attempt_count")) is int
            and int(item["content_gate_attempt_count"]) == 0
            and str(item.get("status") or "") == "pending"
            and str(item.get("content_phase") or "") == "not_started"
            and str(item.get("content_gate_status") or "") == "not_started"
            and all(
                item.get(field) is None
                for field in (
                    "claim_origin_status",
                    "active_generation_request_id",
                    "content_claim_attempt_ordinal",
                    "content_lease_token",
                    "content_lease_expires_at",
                    "content_heartbeat_at",
                    "content_attempt_started_at",
                    "content_provider_attempt_hard_deadline_at",
                    "content_work_unit_deadline_at",
                    "content_gate_passed_at",
                    "content_validation_contract_version",
                    "content_receipt_hash",
                    "active_package_request_id",
                    "package_id",
                    "package_version",
                    "course_id",
                    "course_version",
                    "error_code",
                    "error_message_safe",
                    "completed_at",
                )
            )
        )

    @staticmethod
    def _require_timestamp(value: object, field: str) -> None:
        if type(value) is not int or value < 0:
            raise ValueError(f"{field} must be a non-negative integer")

    @staticmethod
    def _require_positive_int(value: object, field: str) -> None:
        if type(value) is not int or value <= 0:
            raise ValueError(f"{field} must be a positive integer")

    def _reconcile_shared_build_locked(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        target_fingerprint: str,
        now: int,
        require_terminal: bool = False,
        owner_plan_id: str | None = None,
        owner_lease_token: str | None = None,
        owner_handoff_outcome: list[bool] | None = None,
    ) -> int:
        if owner_handoff_outcome is not None:
            owner_handoff_outcome[:] = [False]
        self._validate_identifier(build_id, "build_id")
        self._require_timestamp(now, "now")
        if not isinstance(target_fingerprint, str) or re.fullmatch(
            r"[0-9a-f]{64}", target_fingerprint
        ) is None:
            raise ValueError("target_fingerprint must be canonical SHA-256")
        if (owner_plan_id is None) != (owner_lease_token is None):
            raise ValueError("handoff owner identity must be complete")
        if owner_plan_id is not None:
            self._validate_identifier(owner_plan_id, "owner_plan_id")
            self._validate_identifier(owner_lease_token, "owner_lease_token")
        request_id = f"grade-build:{target_fingerprint}"
        request_digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[
            :24
        ]
        expected_build_id = f"catalog_build_{request_digest}"
        release_id = f"catalog_release_{request_digest}"
        if build_id != expected_build_id:
            return 0
        release = conn.execute(
            "SELECT * FROM learning_catalog_releases "
            "WHERE id = ? LIMIT 1 FOR UPDATE",
            (release_id,),
        ).fetchone()
        build = conn.execute(
            "SELECT * FROM learning_catalog_build_jobs "
            "WHERE id = ? AND release_id = ? LIMIT 1 FOR UPDATE",
            (build_id, release_id),
        ).fetchone()
        items = list(
            conn.execute(
                """
                SELECT * FROM learning_catalog_build_items
                WHERE build_job_id = ?
                ORDER BY subject_ordinal, boundary_ordinal,
                  variant_ordinal, id
                FOR UPDATE
                """,
                (build_id,),
            ).fetchall()
        )
        if release is None or build is None:
            return 0
        if str(build.get("status") or "") == "failed":
            return self._fanout_persisted_terminal_locked(
                conn,
                build_id=build_id,
                release_id=release_id,
                build=build,
                target_fingerprint=target_fingerprint,
                now=now,
            )
        if require_terminal:
            return 0
        terminal = False
        try:
            target = json.loads(str(build["target_spec_json"]))
            canonical_target = self._encode_json(target, sort_keys=True)
            canary_targets = target["canaryManifest"]["targets"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return 0
        if not (
            str(target.get("schemaVersion") or "") == TARGET_SCHEMA_V2
            and str(target.get("gradeCode") or "") == "primary_1"
            and compatible_preparation_target(
                target, build_preparation_target("primary_1")
            )
            and preparation_target_fingerprint(target) == target_fingerprint
            and str(build.get("request_id") or "")
            == f"grade-build:{target_fingerprint}"
            and str(build.get("execution_mode") or "") == "content_only"
            and str(build.get("stage_ceiling") or "") == "content_ready"
            and str(build.get("content_manifest_version") or "")
            == str(target["schemaVersion"])
            and str(build.get("canary_manifest_json") or "")
            == self._encode_json(target["canaryManifest"], sort_keys=True)
            and int(build.get("total_item_count") or 0) == 30
            and len(items) == 30
            and str(build.get("release_id") or "") == release_id
            and str(release.get("id") or "") == release_id
            and str(release.get("status") or "") == "draft"
            and all(
                str(item.get("release_id") or "") == release_id
                and str(item.get("build_job_id") or "") == build_id
                and str(item.get("execution_mode_snapshot") or "")
                == "content_only"
                and str(item.get("content_manifest_version_snapshot") or "")
                == str(target["schemaVersion"])
                for item in items
            )
        ):
            return 0
        auditor = self.content_proof_auditor
        if auditor is None:
            return 0
        try:
            proof_snapshot = auditor(conn, build_id=build_id)
        except Exception:
            return 0
        if not (
            isinstance(proof_snapshot, ContentProofAuditSnapshot)
            and proof_snapshot.build_id == build_id
            and proof_snapshot.release_id == release_id
        ):
            return 0
        item_by_id = {str(item.get("id") or ""): item for item in items}
        if len(item_by_id) != 30:
            return 0
        passed_ids = frozenset(proof_snapshot.passed_item_ids)
        repairable_ids = frozenset(proof_snapshot.repairable_item_ids)
        terminal_failed_ids = frozenset(
            proof_snapshot.terminal_failed_item_ids
        )
        if (
            not (passed_ids | repairable_ids | terminal_failed_ids).issubset(
                item_by_id
            )
            or passed_ids & repairable_ids
            or passed_ids & terminal_failed_ids
            or repairable_ids & terminal_failed_ids
            or any(
                str(item_by_id[item_id].get("status") or "")
                != "course_ready"
                for item_id in passed_ids
            )
            or any(
                str(item_by_id[item_id].get("status") or "") != "failed"
                for item_id in repairable_ids | terminal_failed_ids
            )
        ):
            return 0

        passed = [item for item in items if str(item["id"]) in passed_ids]
        failed = [
            item
            for item in items
            if str(item["id"]) in terminal_failed_ids
        ]
        canary_keys = {
            (
                str(value["subject"]),
                str(value["skillId"]),
                int(value["variantOrdinal"]),
            )
            for value in canary_targets
            if isinstance(value, Mapping)
        }
        if len(canary_keys) != 3:
            return 0
        passed_canaries = sum(
            1
            for item in passed
            if (
                str(item.get("subject") or ""),
                str(item.get("skill_id") or ""),
                int(item.get("variant_ordinal") or 0),
            )
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
        candidate_count = len(passed)
        failed_count = len(failed)
        if candidate_count + failed_count > 30:
            return 0
        handoff = bool(
            candidate_count == 30
            and failed_count == 0
            and passed_canaries == 3
            and failed_canaries == 0
        )
        stage_progress = self._encode_json(
            {
                "candidateCount": candidate_count,
                "canaryCandidateCount": passed_canaries,
                "canaryFailedCount": failed_canaries,
                "canaryTargetCount": 3,
                "failedCount": failed_count,
                "targetCount": 30,
            },
            sort_keys=True,
        )
        progress = max(
            self.STAGE_FLOORS["generating_content"],
            5 + (30 * candidate_count // 30),
        )
        subject_progress = self._encode_json(
            self._content_subject_progress(
                target=target,
                items=items,
                passed_ids=passed_ids,
                failed_ids=terminal_failed_ids,
            )
        )

        hints = list(
            conn.execute(
                """
                SELECT id, family_id, child_id, grade_code,
                  grade_selection_revision, curriculum_version,
                  preparation_contract_version, target_spec_json,
                  target_fingerprint, shared_build_request_id,
                  catalog_build_id, catalog_release_id
                FROM learning_curriculum_preparation_plans
                WHERE target_fingerprint = ?
                  AND shared_build_request_id = ?
                  AND grade_code = 'primary_1'
                  AND status IN ('queued', 'running')
                  AND (catalog_build_id IS NULL OR catalog_build_id = ?)
                  AND (catalog_release_id IS NULL OR catalog_release_id = ?)
                ORDER BY created_at, id
                """,
                (
                    target_fingerprint,
                    build["request_id"],
                    build_id,
                    release_id,
                ),
            ).fetchall()
        )
        if not hints:
            return 0
        hint_by_id = {str(value["id"]): value for value in hints}
        child_ids = sorted(
            {str(value["child_id"]) for value in hints}
        )
        child_markers = ", ".join("?" for _ in child_ids)
        children = list(
            conn.execute(
                f"""
                SELECT * FROM children WHERE id IN ({child_markers})
                ORDER BY family_id, id FOR UPDATE
                """,
                child_ids,
            ).fetchall()
        )
        child_by_id = {str(value["id"]): value for value in children}
        plan_ids = [str(value["id"]) for value in hints]
        plan_markers = ", ".join("?" for _ in plan_ids)
        plans = list(
            conn.execute(
                f"""
                SELECT * FROM learning_curriculum_preparation_plans
                WHERE id IN ({plan_markers})
                ORDER BY created_at, id FOR UPDATE
                """,
                plan_ids,
            ).fetchall()
        )
        updated = 0
        for plan in plans:
            hint = hint_by_id.get(str(plan.get("id") or ""))
            child = child_by_id.get(str(plan["child_id"]))
            live_owner = bool(
                plan.get("lease_token") is not None
                and type(plan.get("lease_expires_at")) is int
                and int(plan["lease_expires_at"]) > int(now)
            )
            try:
                plan_target = json.loads(str(plan["target_spec_json"]))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not (
                hint is not None
                and all(
                    plan.get(field) == hint.get(field)
                    for field in (
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
                )
                and self._plan_owner_matches(plan, child)
                and str(plan.get("grade_code") or "") == "primary_1"
                and type(plan.get("grade_selection_revision")) is int
                and str(plan.get("curriculum_version") or "")
                == str(target.get("curriculumVersion") or "")
                and str(plan.get("preparation_contract_version") or "")
                == str(target.get("preparationContractVersion") or "")
                and self._encode_json(plan_target, sort_keys=True)
                == canonical_target
                and str(plan.get("target_fingerprint") or "")
                == target_fingerprint
                and str(plan.get("shared_build_request_id") or "")
                == str(build.get("request_id") or "")
                and self._catalog_pair_authority_matches(
                    plan,
                    build_id=build_id,
                    release_id=release_id,
                    live_owner=live_owner,
                )
                and str(plan.get("status") or "") in {"queued", "running"}
            ):
                continue
            if terminal:
                error_code = self._catalog_failure_code(build.get("error_code"))
                if proof_trusted:
                    cursor = conn.execute(
                        """
                        UPDATE learning_curriculum_preparation_plans
                        SET status = 'failed', stage = 'completed',
                          catalog_build_id = ?, catalog_release_id = ?,
                          content_target_count = 30,
                          content_canary_target_count = 3,
                          content_candidate_count = ?, content_failed_count = ?,
                          content_canary_candidate_count = ?,
                          content_canary_failed_count = ?,
                          content_canary_passed_at = CASE WHEN ? = 3
                            THEN COALESCE(content_canary_passed_at, ?) ELSE NULL END,
                          stage_progress_json = ?, subject_progress_json = ?,
                          progress_percent = ?, error_code = ?,
                          error_message_safe = ?, completed_at = ?,
                          lease_token = NULL, lease_expires_at = NULL,
                          heartbeat_at = NULL, next_run_at = NULL,
                          hard_deadline_at = NULL, resume_stage = NULL,
                          work_unit_kind = NULL, bound_catalog_item_id = NULL,
                          bound_content_attempt_ordinal = NULL,
                          bound_content_phase = NULL, retry_reason_code = NULL,
                          retry_message_safe = NULL, last_progress_at = ?,
                          updated_at = ?
                        WHERE id = ? AND status IN ('queued', 'running')
                        """,
                        (
                            build_id,
                            release_id,
                            candidate_count,
                            failed_count,
                            passed_canaries,
                            failed_canaries,
                            passed_canaries,
                            int(now),
                            stage_progress,
                            subject_progress,
                            progress,
                            error_code,
                            "课程内容准备失败，请重新准备",
                            int(now),
                            int(now),
                            int(now),
                            plan["id"],
                        ),
                    )
                else:
                    cursor = conn.execute(
                        """
                        UPDATE learning_curriculum_preparation_plans
                        SET status = 'failed', stage = 'completed',
                          catalog_build_id = ?, catalog_release_id = ?,
                          error_code = ?, error_message_safe = ?,
                          completed_at = ?, lease_token = NULL,
                          lease_expires_at = NULL, heartbeat_at = NULL,
                          next_run_at = NULL, hard_deadline_at = NULL,
                          resume_stage = NULL, work_unit_kind = NULL,
                          bound_catalog_item_id = NULL,
                          bound_content_attempt_ordinal = NULL,
                          bound_content_phase = NULL, retry_reason_code = NULL,
                          retry_message_safe = NULL, last_progress_at = ?,
                          updated_at = ?
                        WHERE id = ? AND status IN ('queued', 'running')
                        """,
                        (
                            build_id,
                            release_id,
                            error_code,
                            "课程内容准备失败，请重新准备",
                            int(now),
                            int(now),
                            int(now),
                            plan["id"],
                        ),
                    )
                updated += int(cursor.rowcount == 1)
                continue
            if handoff:
                handoff_authority = self._handoff_authority(
                    plan,
                    now=now,
                    owner_plan_id=owner_plan_id,
                    owner_lease_token=owner_lease_token,
                )
                if handoff_authority == "skip":
                    continue
                authority_clause = (
                    "AND stage = 'generating_content' AND lease_token = ? "
                    "AND lease_expires_at > ? AND catalog_build_id = ? "
                    "AND catalog_release_id = ?"
                    if handoff_authority == "owner"
                    else "AND (lease_expires_at IS NULL OR lease_expires_at <= ?)"
                )
                authority_params = (
                    (owner_lease_token, int(now), build_id, release_id)
                    if handoff_authority == "owner"
                    else (int(now),)
                )
                cursor = conn.execute(
                    f"""
                    UPDATE learning_curriculum_preparation_plans
                    SET status = 'running', stage = 'building_classrooms',
                      catalog_build_id = ?, catalog_release_id = ?,
                      content_target_count = 30,
                      content_canary_target_count = 3,
                      content_candidate_count = 30, content_failed_count = 0,
                      content_canary_candidate_count = 3,
                      content_canary_failed_count = 0,
                      content_canary_passed_at = COALESCE(content_canary_passed_at, ?),
                      content_generation_completed_at =
                        COALESCE(content_generation_completed_at, ?),
                      stage_progress_json = ?, subject_progress_json = ?,
                      progress_percent = 35,
                      ready_course_count = 0, failed_course_count = 0,
                      lease_token = NULL, lease_expires_at = NULL,
                      heartbeat_at = NULL, next_run_at = NULL,
                      hard_deadline_at = NULL, resume_stage = NULL,
                      work_unit_kind = NULL, bound_catalog_item_id = NULL,
                      bound_content_attempt_ordinal = NULL,
                      bound_content_phase = NULL, retry_reason_code = NULL,
                      retry_message_safe = NULL, error_code = NULL,
                      error_message_safe = NULL, last_progress_at = ?,
                      updated_at = ?
                    WHERE id = ? AND status IN ('queued', 'running')
                      {authority_clause}
                    """,
                    (
                        build_id,
                        release_id,
                        int(now),
                        int(now),
                        stage_progress,
                        subject_progress,
                        int(now),
                        int(now),
                        plan["id"],
                        *authority_params,
                    ),
                )
                if (
                    owner_handoff_outcome is not None
                    and handoff_authority == "owner"
                    and cursor.rowcount == 1
                ):
                    owner_handoff_outcome[0] = True
                updated += int(cursor.rowcount == 1)
                continue
            counts_changed = any(int(plan.get(key) or 0) != value for key, value in (
                ("content_candidate_count", candidate_count),
                ("content_failed_count", failed_count),
                ("content_canary_candidate_count", passed_canaries),
                ("content_canary_failed_count", failed_canaries),
            ))
            progress_at = int(now) if counts_changed or not plan.get("last_progress_at") else int(plan["last_progress_at"])
            exact_owner = bool(
                live_owner
                and owner_plan_id is not None
                and owner_lease_token is not None
                and str(plan.get("id") or "") == owner_plan_id
                and str(plan.get("lease_token") or "") == owner_lease_token
                and str(plan.get("status") or "") == "running"
                and str(plan.get("stage") or "") == "generating_content"
            )
            if exact_owner:
                cursor = conn.execute(
                    """
                    UPDATE learning_curriculum_preparation_plans
                    SET catalog_build_id = ?, catalog_release_id = ?,
                      content_target_count = 30,
                      content_canary_target_count = 3,
                      content_candidate_count = ?, content_failed_count = ?,
                      content_canary_candidate_count = ?,
                      content_canary_failed_count = ?,
                      content_canary_passed_at = CASE WHEN ? = 3
                        THEN COALESCE(content_canary_passed_at, ?) ELSE NULL END,
                      stage_progress_json = ?, subject_progress_json = ?,
                      progress_percent = GREATEST(progress_percent, ?),
                      last_progress_at = ?, updated_at = ?
                    WHERE id = ? AND status = 'running'
                      AND stage = 'generating_content' AND lease_token = ?
                      AND lease_expires_at > ? AND catalog_build_id = ?
                      AND catalog_release_id = ?
                    """,
                    (
                        build_id,
                        release_id,
                        candidate_count,
                        failed_count,
                        passed_canaries,
                        failed_canaries,
                        passed_canaries,
                        int(now),
                        stage_progress,
                        subject_progress,
                        progress,
                        progress_at,
                        int(now),
                        plan["id"],
                        owner_lease_token,
                        int(now),
                        build_id,
                        release_id,
                    ),
                )
                updated += int(cursor.rowcount == 1)
                continue
            if live_owner:
                continue
            retry_wait = str(plan.get("stage") or "") == "retry_wait"
            if retry_wait:
                cursor = conn.execute(
                    """
                    UPDATE learning_curriculum_preparation_plans
                    SET catalog_build_id = ?, catalog_release_id = ?,
                      content_target_count = 30,
                      content_canary_target_count = 3,
                      content_candidate_count = ?, content_failed_count = ?,
                      content_canary_candidate_count = ?,
                      content_canary_failed_count = ?,
                      content_canary_passed_at = CASE WHEN ? = 3
                        THEN COALESCE(content_canary_passed_at, ?) ELSE NULL END,
                      stage_progress_json = ?, subject_progress_json = ?,
                      progress_percent = GREATEST(progress_percent, ?),
                      last_progress_at = ?, updated_at = ?
                    WHERE id = ? AND status = 'queued' AND stage = 'retry_wait'
                    """,
                    (
                        build_id,
                        release_id,
                        candidate_count,
                        failed_count,
                        passed_canaries,
                        failed_canaries,
                        passed_canaries,
                        int(now),
                        stage_progress,
                        subject_progress,
                        progress,
                        progress_at,
                        int(now),
                        plan["id"],
                    ),
                )
            else:
                cursor = conn.execute(
                    """
                    UPDATE learning_curriculum_preparation_plans
                    SET status = 'running', stage = 'generating_content',
                      catalog_build_id = ?, catalog_release_id = ?,
                      content_target_count = 30,
                      content_canary_target_count = 3,
                      content_candidate_count = ?, content_failed_count = ?,
                      content_canary_candidate_count = ?,
                      content_canary_failed_count = ?,
                      content_canary_passed_at = CASE WHEN ? = 3
                        THEN COALESCE(content_canary_passed_at, ?) ELSE NULL END,
                      stage_progress_json = ?, subject_progress_json = ?,
                      progress_percent = GREATEST(progress_percent, ?),
                      lease_token = NULL, lease_expires_at = NULL,
                      heartbeat_at = NULL, next_run_at = ?,
                      hard_deadline_at = NULL, resume_stage = NULL,
                      work_unit_kind = NULL, bound_catalog_item_id = NULL,
                      bound_content_attempt_ordinal = NULL,
                      bound_content_phase = NULL, retry_reason_code = NULL,
                      retry_message_safe = NULL, error_code = NULL,
                      error_message_safe = NULL, last_progress_at = ?,
                      updated_at = ?
                    WHERE id = ? AND status IN ('queued', 'running')
                      AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
                    """,
                    (
                        build_id,
                        release_id,
                        candidate_count,
                        failed_count,
                        passed_canaries,
                        failed_canaries,
                        passed_canaries,
                        int(now),
                        stage_progress,
                        subject_progress,
                        progress,
                        int(now) + 1_000,
                        progress_at,
                        int(now),
                        plan["id"],
                        int(now),
                    ),
                )
            updated += int(cursor.rowcount == 1)
        return updated

    def _fanout_persisted_terminal_locked(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        release_id: str,
        build: Mapping[str, object],
        target_fingerprint: str,
        now: int,
    ) -> int:
        shared_request_id = f"grade-build:{target_fingerprint}"
        stable_shared_request = (
            str(build.get("request_id") or "") == shared_request_id
        )
        shared_clause = (
            "OR (shared_build_request_id = ? "
            "AND (catalog_build_id IS NULL OR catalog_build_id = ?) "
            "AND (catalog_release_id IS NULL OR catalog_release_id = ?))"
            if stable_shared_request
            else ""
        )
        params: list[object] = [
            target_fingerprint,
            build_id,
            release_id,
        ]
        if stable_shared_request:
            params.extend(
                (shared_request_id, build_id, release_id)
            )
        hints = list(
            conn.execute(
                f"""
                SELECT id, family_id, child_id
                FROM learning_curriculum_preparation_plans
                WHERE target_fingerprint = ?
                  AND grade_code = 'primary_1'
                  AND status IN ('queued', 'running')
                  AND ((catalog_build_id = ? AND catalog_release_id = ?)
                    {shared_clause})
                ORDER BY created_at, id
                """,
                params,
            ).fetchall()
        )
        if not hints:
            return 0
        child_ids = sorted({str(row["child_id"]) for row in hints})
        child_markers = ", ".join("?" for _ in child_ids)
        children = list(
            conn.execute(
                f"""
                SELECT * FROM children WHERE id IN ({child_markers})
                ORDER BY family_id, id FOR UPDATE
                """,
                child_ids,
            ).fetchall()
        )
        child_by_id = {str(row["id"]): row for row in children}
        plan_ids = [str(row["id"]) for row in hints]
        plan_markers = ", ".join("?" for _ in plan_ids)
        plans = list(
            conn.execute(
                f"""
                SELECT * FROM learning_curriculum_preparation_plans
                WHERE id IN ({plan_markers})
                ORDER BY created_at, id FOR UPDATE
                """,
                plan_ids,
            ).fetchall()
        )
        current_target = build_preparation_target("primary_1")
        error_code = self._catalog_failure_code(build.get("error_code"))
        updated = 0
        for plan in plans:
            child = child_by_id.get(str(plan.get("child_id") or ""))
            try:
                plan_target = json.loads(str(plan["target_spec_json"]))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            exact_bound = bool(
                str(plan.get("catalog_build_id") or "") == build_id
                and str(plan.get("catalog_release_id") or "") == release_id
            )
            shared_follower = bool(
                stable_shared_request
                and str(plan.get("shared_build_request_id") or "")
                == shared_request_id
                and plan.get("catalog_build_id") in {None, build_id}
                and plan.get("catalog_release_id") in {None, release_id}
            )
            if not (
                self._plan_owner_matches(plan, child)
                and (exact_bound or shared_follower)
                and compatible_preparation_target(plan_target, current_target)
                and preparation_target_fingerprint(plan_target)
                == target_fingerprint
                and str(plan.get("target_fingerprint") or "")
                == target_fingerprint
            ):
                continue
            cursor = conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET status = 'failed', stage = 'completed',
                  catalog_build_id = ?, catalog_release_id = ?,
                  error_code = ?, error_message_safe = ?, completed_at = ?,
                  lease_token = NULL, lease_expires_at = NULL,
                  heartbeat_at = NULL, next_run_at = NULL,
                  hard_deadline_at = NULL, resume_stage = NULL,
                  work_unit_kind = NULL, bound_catalog_item_id = NULL,
                  bound_content_attempt_ordinal = NULL,
                  bound_content_phase = NULL, retry_reason_code = NULL,
                  retry_message_safe = NULL, last_progress_at = ?,
                  updated_at = ?
                WHERE id = ? AND status IN ('queued', 'running')
                """,
                (
                    build_id,
                    release_id,
                    error_code,
                    "课程内容准备失败，请重新准备",
                    int(now),
                    int(now),
                    int(now),
                    plan["id"],
                ),
            )
            updated += int(cursor.rowcount == 1)
        return updated

    @staticmethod
    def _content_subject_progress(
        *,
        target: Mapping[str, object],
        items: Sequence[Mapping[str, object]],
        passed_ids: frozenset[str],
        failed_ids: frozenset[str],
    ) -> dict[str, dict[str, int]]:
        targets = target.get("subjectTargets")
        if not isinstance(targets, Mapping):
            raise ValueError("content subject targets are missing")
        item_by_id = {str(item.get("id") or ""): item for item in items}
        if (
            len(item_by_id) != len(items)
            or not passed_ids.isdisjoint(failed_ids)
            or not (passed_ids | failed_ids).issubset(item_by_id)
        ):
            raise ValueError("content subject proof identity drift")
        result: dict[str, dict[str, int]] = {}
        for subject in PREPARATION_SUBJECTS:
            target_row = targets.get(subject)
            if not isinstance(target_row, Mapping):
                raise ValueError("content subject target is missing")
            total = int(target_row.get("totalCourseCount") or 0)
            subject_items = [
                item
                for item in items
                if str(item.get("subject") or "") == subject
            ]
            if total <= 0 or len(subject_items) != total:
                raise ValueError("content subject manifest count drift")
            subject_ids = {
                str(item.get("id") or "") for item in subject_items
            }
            candidate_count = len(subject_ids & passed_ids)
            failed_count = len(subject_ids & failed_ids)
            if candidate_count + failed_count > total:
                raise ValueError("content subject proof count drift")
            result[subject] = {
                "totalCourseCount": total,
                "readyCourseCount": 0,
                "failedCourseCount": 0,
                "contentCandidateCount": candidate_count,
                "contentFailedCount": failed_count,
            }
        if sum(item["totalCourseCount"] for item in result.values()) != len(items):
            raise ValueError("content subject manifest total drift")
        return result

    @staticmethod
    def _catalog_pair_authority_matches(
        plan: Mapping[str, object],
        *,
        build_id: str,
        release_id: str,
        live_owner: bool,
    ) -> bool:
        exact_pair = bool(
            str(plan.get("catalog_build_id") or "") == build_id
            and str(plan.get("catalog_release_id") or "") == release_id
        )
        empty_pair = bool(
            plan.get("catalog_build_id") is None
            and plan.get("catalog_release_id") is None
        )
        return exact_pair or (empty_pair and not live_owner)

    @staticmethod
    def _handoff_authority(
        plan: Mapping[str, object],
        *,
        now: int,
        owner_plan_id: str | None,
        owner_lease_token: str | None,
    ) -> Literal["follower", "owner", "skip"]:
        live_owner = (
            plan.get("lease_token") is not None
            and int(plan.get("lease_expires_at") or 0) > int(now)
        )
        if not live_owner:
            return "follower"
        if (
            owner_plan_id is not None
            and owner_lease_token is not None
            and str(plan.get("id") or "") == owner_plan_id
            and str(plan.get("lease_token") or "") == owner_lease_token
        ):
            return "owner"
        return "skip"

    @staticmethod
    def _is_passed_content_item(item: Mapping[str, object]) -> bool:
        return bool(
            str(item.get("status") or "") == "course_ready"
            and str(item.get("content_phase") or "") == "course_ready"
            and str(item.get("content_gate_status") or "") == "passed"
            and item.get("content_gate_passed_at") is not None
            and isinstance(item.get("content_validation_contract_version"), str)
            and re.fullmatch(
                r"[0-9a-f]{64}", str(item.get("content_receipt_hash") or "")
            )
            is not None
            and item.get("course_id") is not None
            and item.get("course_version") is not None
            and item.get("content_lease_token") is None
            and item.get("content_lease_expires_at") is None
            and item.get("content_work_unit_deadline_at") is None
        )

    @classmethod
    def _catalog_failure_code(cls, value: object) -> str:
        code = str(value or "preparation_generation_failed")
        return code if cls._SAFE_ATOM.fullmatch(code) is not None else "preparation_generation_failed"

    @staticmethod
    def _empty_parent_retry_authority() -> ParentRetryAuthoritySnapshot:
        return ParentRetryAuthoritySnapshot(
            authority_class="not_replayable",
            provider_dispatch_count=0,
            open_or_ambiguous_dispatch_count=0,
            failed_safe_dispatch_count=0,
            provider_graph_complete=False,
            next_work_kind=None,
            build_error_code=None,
        )

    @staticmethod
    def _load_parent_retry_attempt_histories(
        conn: DatabaseConnection,
        *,
        items: Sequence[Mapping[str, object]],
        dispatches: Sequence[Mapping[str, object]],
        lock: bool,
    ) -> dict[str, dict[int, Mapping[str, object]]]:
        rows = list(items)
        if not rows:
            return {}
        requests_by_item = {
            str(row["id"]): {
                1: str(row.get("generation_request_id") or ""),
                2: str(row.get("generation_request_id") or "") + ".attempt2",
            }
            for row in rows
        }
        request_ids = sorted(
            {
                request_id
                for attempts in requests_by_item.values()
                for request_id in attempts.values()
                if request_id
            }
        )
        if not request_ids:
            return {}
        suffix = " FOR UPDATE" if lock else ""
        request_markers = ", ".join("?" for _ in request_ids)
        jobs = list(
            conn.execute(
                f"""
                SELECT * FROM learning_course_generation_jobs
                WHERE request_id IN ({request_markers})
                ORDER BY request_id, id
                """ + suffix,
                request_ids,
            ).fetchall()
        )
        job_ids = sorted({str(job["id"]) for job in jobs})
        candidates: list[DatabaseRow] = []
        if job_ids:
            job_markers = ", ".join("?" for _ in job_ids)
            candidates = list(
                conn.execute(
                    f"""
                    SELECT * FROM learning_course_generation_candidates
                    WHERE job_id IN ({job_markers})
                    ORDER BY job_id, ordinal, id
                    """ + suffix,
                    job_ids,
                ).fetchall()
            )
        candidate_pairs = sorted(
            {
                (str(row["course_id"]), str(row["course_version"]))
                for row in candidates
            }
        )
        course_clauses = [f"generation_request_id IN ({request_markers})"]
        course_params: list[object] = list(request_ids)
        if candidate_pairs:
            pair_markers = ", ".join("(?, ?)" for _ in candidate_pairs)
            course_clauses.append(f"(id, version) IN ({pair_markers})")
            for course_id, course_version in candidate_pairs:
                course_params.extend((course_id, course_version))
        courses = list(
            conn.execute(
                f"""
                SELECT * FROM learning_courses
                WHERE {' OR '.join(course_clauses)}
                ORDER BY id, version
                """ + suffix,
                course_params,
            ).fetchall()
        )
        histories: dict[str, dict[int, Mapping[str, object]]] = {}
        for row in rows:
            item_id = str(row["id"])
            attempts: dict[int, Mapping[str, object]] = {}
            for attempt in (1, 2):
                request_id = requests_by_item[item_id][attempt]
                attempt_jobs = [
                    dict(job)
                    for job in jobs
                    if str(job.get("request_id") or "") == request_id
                ]
                attempt_job_ids = {str(job["id"]) for job in attempt_jobs}
                attempt_candidates = [
                    dict(candidate)
                    for candidate in candidates
                    if str(candidate.get("job_id") or "")
                    in attempt_job_ids
                ]
                attempt_pairs = {
                    (
                        str(candidate.get("course_id") or ""),
                        str(candidate.get("course_version") or ""),
                    )
                    for candidate in attempt_candidates
                }
                attempts[attempt] = {
                    "requestId": request_id,
                    "dispatches": [
                        dict(dispatch)
                        for dispatch in dispatches
                        if str(dispatch.get("build_item_id") or "")
                        == item_id
                        and int(dispatch.get("logical_attempt") or 0)
                        == attempt
                    ],
                    "jobs": attempt_jobs,
                    "candidates": attempt_candidates,
                    "courses": [
                        dict(course)
                        for course in courses
                        if str(course.get("generation_request_id") or "")
                        == request_id
                        or (
                            str(course.get("id") or ""),
                            str(course.get("version") or ""),
                        )
                        in attempt_pairs
                    ],
                }
            histories[item_id] = attempts
        return histories

    def _find_reservation(
        self,
        conn: DatabaseConnection,
        *,
        request_id: str,
        child_id: str,
        grade_selection_revision: int,
        target_fingerprint: str,
    ) -> DatabaseRow | None:
        row = conn.execute(
            """
            SELECT * FROM learning_curriculum_preparation_plans
            WHERE request_id = ? LIMIT 1 FOR UPDATE
            """,
            (request_id,),
        ).fetchone()
        if row is not None:
            return row
        return conn.execute(
            """
            SELECT * FROM learning_curriculum_preparation_plans
            WHERE child_id = ? AND grade_selection_revision = ?
              AND target_fingerprint = ? AND retry_ordinal = 0
            LIMIT 1 FOR UPDATE
            """,
            (child_id, int(grade_selection_revision), target_fingerprint),
        ).fetchone()

    def _find_retry(
        self,
        conn: DatabaseConnection,
        *,
        request_id: str,
        failed_plan_id: str,
    ) -> DatabaseRow | None:
        row = conn.execute(
            """
            SELECT * FROM learning_curriculum_preparation_plans
            WHERE request_id = ? LIMIT 1 FOR UPDATE
            """,
            (request_id,),
        ).fetchone()
        if row is not None:
            return row
        return conn.execute(
            """
            SELECT * FROM learning_curriculum_preparation_plans
            WHERE retry_of_plan_id = ? LIMIT 1 FOR UPDATE
            """,
            (failed_plan_id,),
        ).fetchone()

    @staticmethod
    def _assert_identity(
        row: DatabaseRow,
        *,
        family_id: str,
        child_id: str,
        grade_selection_revision: int,
        target_fingerprint: str,
        retry_of_plan_id: str | None,
        retry_ordinal: int,
    ) -> None:
        actual_retry_source = row["retry_of_plan_id"]
        if (
            row["family_id"] != family_id
            or row["child_id"] != child_id
            or int(row["grade_selection_revision"]) != grade_selection_revision
            or str(row["target_fingerprint"]) != target_fingerprint
            or actual_retry_source != retry_of_plan_id
            or int(row["retry_ordinal"]) != retry_ordinal
        ):
            raise LearningCurriculumPreparationConflict(
                "request is already bound to another preparation plan"
            )

    def _supersede_plan(
        self,
        conn: DatabaseConnection,
        *,
        plan_id: str,
        now: int,
    ) -> bool:
        cursor = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET status = 'superseded', stage = 'completed',
              error_code = NULL, error_message_safe = NULL,
              completed_at = ?, superseded_at = ?, lease_token = NULL,
              lease_expires_at = NULL, heartbeat_at = NULL, next_run_at = NULL,
              hard_deadline_at = NULL, resume_stage = NULL,
              work_unit_kind = NULL, bound_catalog_item_id = NULL,
              bound_content_attempt_ordinal = NULL, bound_content_phase = NULL,
              retry_reason_code = NULL, retry_message_safe = NULL,
              updated_at = ?
            WHERE id = ? AND status IN ('queued', 'running')
            """,
            (int(now), int(now), int(now), plan_id),
        )
        return cursor.rowcount == 1

    @classmethod
    def _supported_stages(
        cls, requested: Sequence[str] | None
    ) -> tuple[str, ...]:
        if requested is None:
            return cls.CLAIMABLE_STAGES
        requested_set = {str(stage) for stage in requested}
        unsupported = requested_set.difference(cls.CLAIMABLE_STAGES)
        if unsupported:
            raise ValueError("unsupported preparation claim stage")
        return tuple(
            stage for stage in cls.CLAIMABLE_STAGES if stage in requested_set
        )

    @staticmethod
    def _validate_plan_target(plan: DatabaseRow) -> None:
        target = json.loads(str(plan["target_spec_json"]))
        if preparation_target_fingerprint(target) != str(plan["target_fingerprint"]):
            raise LearningCurriculumPreparationConflict(
                "persisted preparation target fingerprint mismatch"
            )
        if str(target.get("gradeCode")) != str(plan["grade_code"]):
            raise LearningCurriculumPreparationConflict(
                "persisted preparation target grade mismatch"
            )

    @staticmethod
    def _claim_matches(
        plan: DatabaseRow | None,
        *,
        lease_token: str,
        target_fingerprint: str,
        expected_stage: str,
        now: int,
    ) -> bool:
        return bool(
            plan is not None
            and str(plan["status"]) == "running"
            and str(plan["stage"]) == expected_stage
            and str(plan["lease_token"] or "") == lease_token
            and str(plan["target_fingerprint"]) == target_fingerprint
            and plan.get("lease_expires_at") is not None
            and int(plan["lease_expires_at"]) > int(now)
        )

    @staticmethod
    def _initial_subject_progress(
        target: Mapping[str, Any],
    ) -> dict[str, dict[str, int]]:
        targets = target.get("subjectTargets")
        if not isinstance(targets, Mapping):
            raise ValueError("preparation target subjectTargets must be an object")
        result: dict[str, dict[str, int]] = {}
        for subject in PREPARATION_SUBJECTS:
            item = targets.get(subject)
            if not isinstance(item, Mapping):
                raise ValueError("preparation target is missing a subject")
            total = int(item.get("totalCourseCount") or 0)
            if total <= 0:
                raise ValueError("preparation subject total must be positive")
            result[subject] = {
                "totalCourseCount": total,
                "readyCourseCount": 0,
                "failedCourseCount": 0,
            }
            if str(target.get("schemaVersion") or "") == TARGET_SCHEMA_V2:
                result[subject].update(
                    {
                        "contentCandidateCount": 0,
                        "contentFailedCount": 0,
                    }
                )
        return result

    @classmethod
    def _initial_content_progress(cls, target: Mapping[str, Any]) -> dict[str, int]:
        if str(target.get("schemaVersion") or "") == TARGET_SCHEMA_V2:
            target_count = int(target.get("totalCourseCount") or 0)
            canary = target.get("canaryManifest")
            canary_targets = (
                canary.get("targets") if isinstance(canary, Mapping) else None
            )
            if target_count != 30 or not isinstance(canary_targets, list):
                raise ValueError("v2 preparation target content evidence mismatch")
            canary_target_count = len(canary_targets)
            if canary_target_count != 3:
                raise ValueError("v2 preparation target canary evidence mismatch")
        else:
            target_count = 0
            canary_target_count = 0
        return {
            "candidateCount": 0,
            "canaryCandidateCount": 0,
            "canaryFailedCount": 0,
            "canaryTargetCount": canary_target_count,
            "failedCount": 0,
            "targetCount": target_count,
        }

    @staticmethod
    def _is_v2_plan(plan: DatabaseRow) -> bool:
        target = json.loads(str(plan["target_spec_json"]))
        return str(target.get("schemaVersion") or "") == TARGET_SCHEMA_V2

    @classmethod
    def _validate_progress_counts(
        cls,
        plan: DatabaseRow,
        *,
        ready_course_count: int,
        failed_course_count: int,
        subject_progress: Mapping[str, Any],
        monotonic: bool,
    ) -> None:
        ready = int(ready_course_count)
        failed = int(failed_course_count)
        total = int(plan["total_course_count"])
        if ready < 0 or failed < 0 or ready + failed > total:
            raise ValueError("invalid preparation course counts")
        if monotonic and (
            ready < int(plan["ready_course_count"])
            or failed < int(plan["failed_course_count"])
        ):
            raise ValueError("preparation course counts cannot decrease")
        if list(subject_progress) != list(PREPARATION_SUBJECTS):
            raise ValueError("subject progress must use canonical subject order")
        target = json.loads(str(plan["target_spec_json"]))
        target_subjects = target["subjectTargets"]
        is_v2 = str(target.get("schemaVersion") or "") == TARGET_SCHEMA_V2
        expected_keys = {
            "totalCourseCount",
            "readyCourseCount",
            "failedCourseCount",
        }
        if is_v2:
            expected_keys |= {
                "contentCandidateCount",
                "contentFailedCount",
            }
        subject_total = 0
        subject_ready = 0
        subject_failed = 0
        subject_content_candidate = 0
        subject_content_failed = 0
        for subject in PREPARATION_SUBJECTS:
            item = subject_progress.get(subject)
            if not isinstance(item, Mapping):
                raise ValueError("subject progress entry must be an object")
            if set(item) != expected_keys or any(
                type(item[key]) is not int for key in expected_keys
            ):
                raise ValueError("subject progress entry shape is invalid")
            item_total = item["totalCourseCount"]
            item_ready = item["readyCourseCount"]
            item_failed = item["failedCourseCount"]
            expected_total = int(target_subjects[subject]["totalCourseCount"])
            if (
                item_total != expected_total
                or item_ready < 0
                or item_failed < 0
                or item_ready + item_failed > item_total
            ):
                raise ValueError("subject progress counts are inconsistent")
            subject_total += item_total
            subject_ready += item_ready
            subject_failed += item_failed
            if is_v2:
                item_content_candidate = item["contentCandidateCount"]
                item_content_failed = item["contentFailedCount"]
                if (
                    item_content_candidate < 0
                    or item_content_failed < 0
                    or item_content_candidate + item_content_failed > item_total
                ):
                    raise ValueError(
                        "subject content progress counts are inconsistent"
                    )
                subject_content_candidate += item_content_candidate
                subject_content_failed += item_content_failed
        if (
            subject_total != total
            or subject_ready != ready
            or subject_failed != failed
        ):
            raise ValueError("subject progress sums do not match plan counts")
        if is_v2 and (
            subject_content_candidate != int(plan["content_candidate_count"])
            or subject_content_failed != int(plan["content_failed_count"])
        ):
            raise ValueError(
                "subject content progress sums do not match plan counts"
            )

    @classmethod
    def _progress_percent(
        cls,
        stage: str,
        *,
        ready_course_count: int,
        failed_course_count: int,
        total_course_count: int,
        previous: int,
    ) -> int:
        if stage == "completed":
            return 100
        floor = cls.STAGE_FLOORS[stage]
        ordered = tuple(cls.STAGE_FLOORS)
        next_floor = cls.STAGE_FLOORS[ordered[ordered.index(stage) + 1]]
        completed_items = min(
            total_course_count, ready_course_count + failed_course_count
        )
        interpolated = floor + int(
            (next_floor - floor) * completed_items / max(1, total_course_count)
        )
        return max(int(previous), min(next_floor - 1, interpolated))

    @classmethod
    def _validate_event_payload(
        cls, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        safe: dict[str, Any] = {}
        for key, value in payload.items():
            key_text = str(key)
            is_id = key_text.endswith("Id")
            is_count = key_text.endswith("Count")
            if not (is_id or is_count or key_text in cls._SAFE_EVENT_KEYS):
                raise ValueError("event payload contains a non-public field")
            if is_count or key_text in {"retryOrdinal", "progressPercent"}:
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError("event count must be a non-negative integer")
            elif not isinstance(value, str) or cls._SAFE_ATOM.fullmatch(value) is None:
                raise ValueError("event identifiers and codes must be safe atoms")
            safe[key_text] = value
        return safe

    @classmethod
    def _safe_code(cls, value: object) -> str:
        text = str(value or "preparation_failed").strip()
        if cls._SAFE_ATOM.fullmatch(text) is None or len(text) > 128:
            return "preparation_failed"
        return text

    @staticmethod
    def _validate_identifier(value: object, field: str) -> None:
        text = str(value or "")
        if not text or len(text) > 128:
            raise ValueError(f"{field} must be 1 to 128 characters")

    @staticmethod
    def _stable_id(prefix: str, identity: str) -> str:
        digest = hashlib.sha256(
            f"mira.learning.preparation:{identity}".encode("utf-8")
        ).hexdigest()[:40]
        return f"{prefix}_{digest}"

    @staticmethod
    def _encode_json(payload: Mapping[str, Any], *, sort_keys: bool = False) -> str:
        return json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=sort_keys,
            separators=(",", ":"),
        )
