from __future__ import annotations

from integrations.openmaic_formal_media import compatible_preparation_target

import hashlib
import json
import re
from pathlib import Path
from typing import Callable, Mapping

from core.database import Database, DatabaseConnection
from core.errors import ApiError
from core.security import now_ms as current_time_ms
from repositories.learning_curriculum_preparation_repository import (
    LearningCurriculumPreparationConflict,
    LearningCurriculumPreparationRepository,
    ParentRetryAuthoritySnapshot,
)
from repositories.learning_repository import LearningRepository
from schemas.education import grade_definition_for_code
from services.auth_service import AuthService
from services.learning_curriculum_preparation_contract import (
    MAX_PARENT_RETRIES,
    PREPARATION_SCHEMA_V2,
    PREPARATION_SCHEMA_VERSION,
    PREPARATION_SUBJECTS,
    TARGET_SCHEMA_V2,
    build_preparation_target,
    preparation_target_fingerprint,
)
from services.formal_student_learning_access import (
    FORMAL_STUDENT_GRADE_CODES,
    formal_student_release_available,
    assert_formal_student_workspace_open,
)


PRIMARY_GRADE_CODES = {f"primary_{grade}" for grade in range(1, 7)}
SUBJECT_LABELS = {"chinese": "语文", "math": "数学", "english": "英语"}
RETRY_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
PREPARATION_NOT_FOUND = (
    "learning_preparation_not_found",
    "课程准备计划不存在",
    404,
)
PREPARATION_NOT_RETRYABLE = (
    "learning_preparation_not_retryable",
    "当前课程准备计划不可重试",
    409,
)
PREPARATION_SCHEMA_NOT_ACCEPTABLE = (
    "learning_preparation_schema_not_acceptable",
    "不支持的课程准备数据版本",
    406,
)
PREPARATION_STATE_INVALID = (
    "learning_preparation_state_invalid",
    "课程准备状态暂时不可用",
    409,
)
PARENT_RETRYABLE_DEPENDENCY_ERRORS = frozenset(
    {
        "preparation_dependency_unavailable",
        "preparation_stage_deadline_exceeded",
        "preparation_content_stage_deadline_exceeded",
    }
)


def _not_replayable_retry_authority() -> ParentRetryAuthoritySnapshot:
    return ParentRetryAuthoritySnapshot(
        authority_class="not_replayable",
        provider_dispatch_count=0,
        open_or_ambiguous_dispatch_count=0,
        failed_safe_dispatch_count=0,
        provider_graph_complete=False,
        next_work_kind=None,
        build_error_code=None,
    )
PUBLIC_ERROR_MESSAGES = {
    "preparation_dependency_unavailable": "课程服务暂时不可用，请稍后重试",
    "preparation_generation_failed": "课程准备暂时失败，请稍后重试",
    "preparation_catalog_conflict": "课程目录请求冲突，请重新准备",
    "preparation_stage_deadline_exceeded": "课程准备时间较长，请重新准备",
    "preparation_validation_failed": "部分课程未通过系统校验，请重新准备",
    "preparation_upgrade_retry_state_invalid": "课程准备重试状态已安全终止，请重新准备",
}
GENERIC_PUBLIC_ERROR = {
    "code": "preparation_failed",
    "message": "课程准备暂时失败，请稍后重试",
}


def parent_retry_decision(
    plan: Mapping[str, object],
    build_snapshot: ParentRetryAuthoritySnapshot,
) -> bool:
    """Return the sole public retry decision from sealed, non-secret facts."""
    if not isinstance(build_snapshot, ParentRetryAuthoritySnapshot):
        return False
    snapshot_counts = (
        build_snapshot.provider_dispatch_count,
        build_snapshot.open_or_ambiguous_dispatch_count,
        build_snapshot.failed_safe_dispatch_count,
    )
    if not (
        str(plan.get("status") or "") == "failed"
        and str(plan.get("stage") or "") == "completed"
        and type(plan.get("retry_ordinal")) is int
        and int(plan["retry_ordinal"]) == 0
        and str(plan.get("error_code") or "")
        in PARENT_RETRYABLE_DEPENDENCY_ERRORS
        and type(plan.get("completed_at")) is int
        and isinstance(plan.get("error_message_safe"), str)
        and bool(str(plan["error_message_safe"]))
        and isinstance(plan.get("catalog_build_id"), str)
        and bool(str(plan["catalog_build_id"]))
        and isinstance(plan.get("catalog_release_id"), str)
        and bool(str(plan["catalog_release_id"]))
        and plan.get("retry_of_plan_id") is None
        and plan.get("superseded_at") is None
        and all(type(value) is int and value >= 0 for value in snapshot_counts)
        and all(
            plan.get(key) is None
            for key in (
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
        and build_snapshot.open_or_ambiguous_dispatch_count == 0
        and build_snapshot.failed_safe_dispatch_count == 0
        and build_snapshot.build_error_code is None
    ):
        return False
    if build_snapshot.authority_class == "pre_provider_dependency":
        return bool(
            build_snapshot.provider_dispatch_count == 0
            and build_snapshot.provider_graph_complete is False
            and build_snapshot.next_work_kind is None
        )
    if build_snapshot.authority_class == "host_only_dependency":
        return bool(
            build_snapshot.provider_dispatch_count > 0
            and build_snapshot.provider_graph_complete is True
            and build_snapshot.next_work_kind == "host_gate"
        )
    return False


class LearningCurriculumPreparationService:
    def __init__(
        self,
        database_url: str | Path,
        *,
        auth_service: AuthService,
        course_library_enabled: bool = False,
        repository: LearningCurriculumPreparationRepository | None = None,
        learning_repository: LearningRepository | None = None,
        retry_repository_factory: Callable[
            [], LearningCurriculumPreparationRepository
        ]
        | None = None,
        shared_build_repository_factory: Callable[
            [], LearningCurriculumPreparationRepository
        ]
        | None = None,
    ):
        database = Database(database_url)
        self.database_url = database.database_url
        self.course_library_enabled = course_library_enabled
        self.auth_service = auth_service
        self.repository = repository or LearningCurriculumPreparationRepository(database)
        self.learning_repository = learning_repository or LearningRepository(database)
        self.retry_repository_factory = retry_repository_factory or (
            lambda: self.repository
        )
        self.shared_build_repository_factory = shared_build_repository_factory

    def next_grade_selection_revision(
        self,
        current: Mapping[str, object] | None,
        *,
        grade_code: str | None,
        school_year_start_year: int | None,
    ) -> int:
        previous = (
            str((current or {}).get("grade_code") or ""),
            int((current or {}).get("grade_school_year_start") or 0),
        )
        incoming = (str(grade_code or ""), int(school_year_start_year or 0))
        revision = int((current or {}).get("grade_selection_revision") or 0)
        if incoming == ("", 0):
            return revision
        if current is not None and previous == incoming:
            return revision
        return revision + 1

    def reserve_for_saved_child(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child: Mapping[str, object],
        now: int,
    ) -> dict[str, object] | None:
        grade_code = str(child.get("grade_code") or "")
        if grade_code not in FORMAL_STUDENT_GRADE_CODES:
            self.repository.supersede_current_nonterminal(
                conn,
                family_id=family_id,
                child_id=str(child["id"]),
                now=now,
            )
            return None

        target = build_preparation_target(grade_code)
        fingerprint = preparation_target_fingerprint(target)
        revision = int(child["grade_selection_revision"])
        request_digest = hashlib.sha256(
            f"{child['id']}|{revision}|{fingerprint}".encode("utf-8")
        ).hexdigest()
        request_id = f"grade-prep:{request_digest}"
        shared_id = f"grade-build:{fingerprint}"
        plan, _ = self.repository.reserve_plan(
            conn,
            family_id=family_id,
            child_id=str(child["id"]),
            grade_code=grade_code,
            school_year_start_year=int(child["grade_school_year_start"]),
            grade_selection_revision=revision,
            target=target,
            target_fingerprint=fingerprint,
            request_id=request_id,
            shared_build_request_id=shared_id,
            now=now,
        )
        adopted = self.repository.adopt_active_formal_release(
            conn,
            plan_id=str(plan["id"]),
            family_id=family_id,
            child_id=str(child["id"]),
            grade_selection_revision=revision,
            target_fingerprint=fingerprint,
            now=now,
        )
        if adopted is not None:
            plan = adopted
        if (
            self.shared_build_repository_factory is not None
            and str(plan.get("status") or "") == "queued"
            and str(plan.get("stage") or "") == "queued"
        ):
            # Reuse persisted, locally verified work immediately. A parent
            # saving a grade must not wait behind another child's long model
            # call merely to see a classroom that is already published.
            build_digest = hashlib.sha256(shared_id.encode("utf-8")).hexdigest()[:24]
            shared_repository = self.shared_build_repository_factory()
            shared_repository.reconcile_shared_build(
                conn,
                build_id=f"catalog_build_{build_digest}",
                target_fingerprint=fingerprint,
                now=now,
            )
            plan = self.repository.get_plan(conn, str(plan["id"])) or plan
        self.repository.supersede_other_nonterminal(
            conn,
            family_id=family_id,
            child_id=str(child["id"]),
            keep_plan_id=str(plan["id"]),
            now=now,
        )
        return self.preparation_payload(plan, now_ms=now)

    @staticmethod
    def availability_payload(
        grade_code: object,
        preparation: Mapping[str, object] | None,
    ) -> dict[str, object] | None:
        normalized = str(grade_code or "")
        if normalized not in PRIMARY_GRADE_CODES:
            return None
        if normalized not in FORMAL_STUDENT_GRADE_CODES:
            return {
                "status": "unavailable",
                "gradeCode": normalized,
                "message": "该年级正式课程尚未开放",
            }
        if preparation is None:
            return None
        return {
            "status": "preparing",
            "gradeCode": normalized,
            "message": "已开始准备",
        }

    def current(
        self,
        access_token: str,
        query: Mapping[str, object],
        *,
        schema_header_present: bool = False,
        requested_schema: str | None = None,
    ) -> dict[str, object]:
        context = self.auth_service.authenticate(access_token)
        child_id = str(query.get("childId") or "").strip()
        if not child_id:
            raise ApiError("missing_child_id", "请选择孩子")
        family_id = str(context["family"]["id"])
        now = current_time_ms()
        with self.repository.transaction() as conn:
            child = conn.execute(
                "SELECT * FROM children WHERE family_id = ? AND id = ?",
                (family_id, child_id),
            ).fetchone()
            if child is None:
                raise ApiError(*PREPARATION_NOT_FOUND)
            response_schema = self._negotiate_schema(
                header_present=schema_header_present,
                requested_schema=requested_schema,
            )
            grade_code = str(child.get("grade_code") or "")
            if grade_code not in FORMAL_STUDENT_GRADE_CODES:
                response: dict[str, object] = {
                    "ok": True,
                    "preparation": None,
                }
                availability = self.availability_payload(grade_code, None)
                if availability is not None:
                    response["learningPreparationAvailability"] = availability
                return response
            target_fingerprint = preparation_target_fingerprint(
                build_preparation_target(grade_code)
            )
            plan = self.repository.get_current_for_child(
                conn,
                family_id=family_id,
                child_id=child_id,
                grade_selection_revision=int(child["grade_selection_revision"]),
                target_fingerprint=target_fingerprint,
            )
        retry_authority = None
        if plan is not None and str(plan.get("status") or "") == "failed":
            retry_repository = self.retry_repository_factory()
            with retry_repository.transaction() as conn:
                retry_authority = retry_repository.load_parent_retry_authority(
                    conn,
                    plan=plan,
                    lock=False,
                )
        return {
            "ok": True,
            "preparation": (
                self.preparation_payload(
                    plan,
                    now_ms=now,
                    schema_version=response_schema,
                    retry_authority=retry_authority,
                )
                if plan is not None
                else None
            ),
        }

    def learning_availability(
        self,
        access_token: str,
        query: Mapping[str, object],
    ) -> dict[str, object]:
        context = self.auth_service.authenticate(access_token)
        child_id = str(query.get("childId") or "").strip()
        if not child_id:
            raise ApiError("missing_child_id", "请选择孩子")
        family_id = str(context["family"]["id"])
        with self.repository.transaction() as conn:
            child = conn.execute(
                "SELECT * FROM children WHERE family_id = ? AND id = ?",
                (family_id, child_id),
            ).fetchone()
            if child is None:
                raise ApiError(*PREPARATION_NOT_FOUND)
            grade_code = str(child.get("grade_code") or "")
            has_active_release = formal_student_release_available(conn, child)
            try:
                assert_formal_student_workspace_open(child)
                can_access_workspace = True
            except ApiError:
                can_access_workspace = False
            available_course_count = 0
            if (
                grade_code in FORMAL_STUDENT_GRADE_CODES
                and int(child.get("grade_selection_revision") or 0) >= 1
            ):
                summary = self.learning_repository.student_catalog_summary(
                    conn,
                    family_id=family_id,
                    child_id=child_id,
                    grade_code=grade_code,
                    grade_selection_revision=int(
                        child.get("grade_selection_revision") or 0
                    ),
                )
                available_course_count = int(
                    summary["availableCourseCount"]
                )
        return {
            "ok": True,
            "availability": {
                "gradeCode": grade_code,
                # Opt in because older mobile clients require exact response keys.
                **(
                    {"canAccessWorkspace": can_access_workspace}
                    if query.get("includeWorkspaceAccess") == "true"
                    else {}
                ),
                "hasActiveRelease": has_active_release,
                "availableCourseCount": available_course_count,
                "canLearnNow": bool(
                    has_active_release or available_course_count > 0
                ),
            },
        }

    def retry(
        self,
        access_token: str,
        plan_id: str,
        data_loader: Callable[[], object],
        *,
        schema_header_present: bool = False,
        requested_schema: str | None = None,
    ) -> tuple[dict[str, object], bool]:
        context = self.auth_service.authenticate(access_token)
        family_id = str(context["family"]["id"])
        with self.repository.transaction() as conn:
            source_hint = self.repository.get_plan_for_family(
                conn,
                family_id=family_id,
                plan_id=plan_id,
            )
        if source_hint is None:
            raise ApiError(*PREPARATION_NOT_FOUND)
        if str(source_hint.get("grade_code") or "") not in FORMAL_STUDENT_GRADE_CODES:
            raise ApiError(*PREPARATION_NOT_RETRYABLE)
        response_schema = self._negotiate_schema(
            header_present=schema_header_present,
            requested_schema=requested_schema,
        )
        data = data_loader()
        if type(data) is not dict:
            raise ApiError("invalid_request", "请求参数不正确")
        if set(data) != {"requestId"}:
            raise ApiError("invalid_request", "请求参数不正确")
        client_request_id = data["requestId"]
        if type(client_request_id) is not str:
            raise ApiError("invalid_request_id", "重试请求编号格式不正确")
        if RETRY_REQUEST_ID.fullmatch(client_request_id) is None:
            raise ApiError("invalid_request_id", "重试请求编号格式不正确")
        now = current_time_ms()
        retry_digest = hashlib.sha256(
            f"{family_id}|{plan_id}|{client_request_id}".encode("utf-8")
        ).hexdigest()
        stored_retry_request_id = f"grade-prep-retry:{retry_digest}"
        retry_repository = self.retry_repository_factory()
        with retry_repository.transaction() as conn:
            locked_context = retry_repository.lock_parent_retry_context(
                conn,
                family_id=family_id,
                plan_id=plan_id,
            )
            if locked_context is None:
                raise ApiError(*PREPARATION_NOT_FOUND)
            child, source, retry_authority = locked_context

            live_grade_code = str(child.get("grade_code") or "")
            live_school_year = int(child.get("grade_school_year_start") or 0)
            try:
                persisted_target = json.loads(str(source.get("target_spec_json") or "{}"))
                target_compatible = live_grade_code in FORMAL_STUDENT_GRADE_CODES and compatible_preparation_target(
                    persisted_target, build_preparation_target(live_grade_code)
                )
                current_fingerprint = preparation_target_fingerprint(persisted_target) if target_compatible else ""
            except (TypeError, ValueError):
                current_fingerprint = ""
            if (
                live_grade_code not in FORMAL_STUDENT_GRADE_CODES
                or str(source["grade_code"]) not in FORMAL_STUDENT_GRADE_CODES
                or str(source["grade_code"]) != live_grade_code
                or int(source["school_year_start_year"]) != live_school_year
                or int(source["grade_selection_revision"])
                != int(child["grade_selection_revision"])
                or str(source["target_fingerprint"]) != current_fingerprint
            ):
                raise ApiError(*PREPARATION_NOT_RETRYABLE)
            if not parent_retry_decision(source, retry_authority):
                raise ApiError(*PREPARATION_NOT_RETRYABLE)

            current = retry_repository.get_current_for_child(
                conn,
                family_id=family_id,
                child_id=str(child["id"]),
                grade_selection_revision=int(child["grade_selection_revision"]),
                target_fingerprint=current_fingerprint,
            )
            if current is None:
                raise ApiError(*PREPARATION_NOT_RETRYABLE)
            if str(current["id"]) != str(source["id"]):
                if self._is_retry_successor(
                    current,
                    source=source,
                    stored_retry_request_id=stored_retry_request_id,
                ):
                    return {
                        "ok": True,
                        "preparation": self.preparation_payload(
                            current,
                            now_ms=now,
                            schema_version=response_schema,
                        ),
                    }, False
                raise ApiError(*PREPARATION_NOT_RETRYABLE)

            try:
                successor, created = retry_repository.create_retry_successor(
                    conn,
                    failed_plan_id=plan_id,
                    family_id=family_id,
                    request_id=stored_retry_request_id,
                    now=now,
                )
            except (LearningCurriculumPreparationConflict, ValueError):
                raise ApiError(*PREPARATION_NOT_RETRYABLE)
            if not self._is_retry_successor(
                successor,
                source=source,
                stored_retry_request_id=stored_retry_request_id,
            ):
                raise ApiError(*PREPARATION_NOT_RETRYABLE)
            return {
                "ok": True,
                "preparation": self.preparation_payload(
                    successor,
                    now_ms=now,
                    schema_version=response_schema,
                ),
            }, created

    @staticmethod
    def _is_retry_successor(
        row: Mapping[str, object],
        *,
        source: Mapping[str, object],
        stored_retry_request_id: str,
    ) -> bool:
        return (
            str(row.get("request_id") or "") == stored_retry_request_id
            and str(row.get("family_id") or "") == str(source["family_id"])
            and str(row.get("child_id") or "") == str(source["child_id"])
            and str(row.get("retry_of_plan_id") or "") == str(source["id"])
            and int(row.get("retry_ordinal") or 0) == 1
            and int(
                row.get("grade_selection_revision")
                if row.get("grade_selection_revision") is not None
                else -1
            )
            == int(source["grade_selection_revision"])
            and str(row.get("target_fingerprint") or "")
            == str(source["target_fingerprint"])
            and str(row.get("grade_code") or "") == str(source["grade_code"])
            and int(row.get("school_year_start_year") or 0)
            == int(source["school_year_start_year"])
        )

    def preparation_payload(
        self,
        row: Mapping[str, object],
        *,
        now_ms: int,
        schema_version: str = PREPARATION_SCHEMA_VERSION,
        retry_authority: ParentRetryAuthoritySnapshot | None = None,
    ) -> dict[str, object]:
        subject_progress = json.loads(str(row["subject_progress_json"]))
        content_progress: dict[str, object] | None = None
        if schema_version == PREPARATION_SCHEMA_V2:
            subject_progress, content_progress = self._validated_v2_progress(row)
        grade_label = grade_definition_for_code(row["grade_code"]).label
        status = str(row["status"])
        subjects = [
            {
                "code": subject,
                "label": SUBJECT_LABELS[subject],
                "readyCourseCount": int(subject_progress[subject]["readyCourseCount"]),
                "failedCourseCount": int(subject_progress[subject]["failedCourseCount"]),
                "totalCourseCount": int(subject_progress[subject]["totalCourseCount"]),
                **(
                    {
                        "contentCandidateCount": int(
                            subject_progress[subject]["contentCandidateCount"]
                        ),
                        "contentFailedCount": int(
                            subject_progress[subject]["contentFailedCount"]
                        ),
                    }
                    if schema_version == PREPARATION_SCHEMA_V2
                    else {}
                ),
            }
            for subject in PREPARATION_SUBJECTS
        ]
        payload = {
            "schemaVersion": schema_version,
            "id": str(row["id"]),
            "childId": str(row["child_id"]),
            "gradeCode": str(row["grade_code"]),
            "gradeLabel": grade_label,
            "subjects": subjects,
            "status": status,
            "stage": str(row["stage"]),
            "progressPercent": int(row["progress_percent"]),
            "totalCourseCount": int(row["total_course_count"]),
            "readyCourseCount": int(row["ready_course_count"]),
            "failedCourseCount": int(row["failed_course_count"]),
            "attempt": int(row["retry_ordinal"]) + 1,
            "canRetry": parent_retry_decision(
                row,
                retry_authority or _not_replayable_retry_authority(),
            ),
            "retryAfterMs": self._retry_after_ms(row, now_ms=now_ms),
            "message": self._parent_message(row, grade_label=grade_label),
            "lastProgressAt": row.get("last_progress_at"),
            "updatedAt": int(row["updated_at"]),
            "completedAt": row.get("completed_at"),
            "error": self._public_safe_error(row),
        }
        if content_progress is not None:
            payload["contentProgress"] = content_progress
        if self.course_library_enabled:
            from services.course_library_service import cached_supply_summary
            supply = cached_supply_summary(self.database_url, grade_code=str(row["grade_code"]))
            if supply is not None:
                payload["courseSupply"] = supply
                if supply["paused"] or supply.get("delayed"):
                    payload["retryAfterMs"] = 30000
                    payload["message"] = supply["message"]
        return payload

    @staticmethod
    def _validated_v2_progress(
        row: Mapping[str, object],
    ) -> tuple[Mapping[str, object], dict[str, object]]:
        try:
            target = json.loads(str(row["target_spec_json"]))
            subject_progress = json.loads(str(row["subject_progress_json"]))
            stage_progress = json.loads(str(row["stage_progress_json"]))
            if not isinstance(target, Mapping):
                raise ValueError("target must be an object")
            if (
                str(target.get("schemaVersion") or "") != TARGET_SCHEMA_V2
                or str(target.get("gradeCode") or "") != "primary_1"
                or str(row.get("grade_code") or "") != "primary_1"
                or not compatible_preparation_target(target, build_preparation_target("primary_1"))
                or str(row.get("target_fingerprint") or "")
                != preparation_target_fingerprint(target)
            ):
                raise ValueError("v2 target authority drift")
            content_keys = (
                "content_candidate_count",
                "content_failed_count",
                "content_target_count",
                "content_canary_candidate_count",
                "content_canary_failed_count",
                "content_canary_target_count",
            )
            if any(type(row.get(key)) is not int for key in content_keys):
                raise ValueError("v2 content count type drift")
            candidate = row["content_candidate_count"]
            failed = row["content_failed_count"]
            target_count = row["content_target_count"]
            canary_candidate = row["content_canary_candidate_count"]
            canary_failed = row["content_canary_failed_count"]
            canary_target = row["content_canary_target_count"]
            if not (
                target_count == 30
                and canary_target == 3
                and candidate >= 0
                and failed >= 0
                and candidate + failed <= target_count
                and canary_candidate >= 0
                and canary_failed >= 0
                and canary_candidate + canary_failed <= canary_target
                and canary_candidate <= candidate
                and canary_failed <= failed
            ):
                raise ValueError("v2 content count invariant drift")
            passed = row.get("content_canary_passed_at") is not None
            if passed != (
                canary_candidate == canary_target == 3 and canary_failed == 0
            ):
                raise ValueError("v2 canary evidence drift")
            expected_stage = {
                "candidateCount": candidate,
                "canaryCandidateCount": canary_candidate,
                "canaryFailedCount": canary_failed,
                "canaryTargetCount": canary_target,
                "failedCount": failed,
                "targetCount": target_count,
            }
            if (
                not isinstance(stage_progress, Mapping)
                or set(stage_progress) != set(expected_stage)
                or any(type(stage_progress[key]) is not int for key in expected_stage)
                or dict(stage_progress) != expected_stage
            ):
                raise ValueError("v2 stage progress drift")
            if not isinstance(subject_progress, Mapping) or list(
                subject_progress
            ) != list(PREPARATION_SUBJECTS):
                raise ValueError("v2 subject set drift")
            expected_subject_keys = {
                "totalCourseCount",
                "readyCourseCount",
                "failedCourseCount",
                "contentCandidateCount",
                "contentFailedCount",
            }
            subject_totals = {
                "total": 0,
                "ready": 0,
                "failed": 0,
                "candidate": 0,
                "content_failed": 0,
            }
            for subject in PREPARATION_SUBJECTS:
                item = subject_progress.get(subject)
                if (
                    not isinstance(item, Mapping)
                    or set(item) != expected_subject_keys
                    or any(type(item[key]) is not int for key in expected_subject_keys)
                ):
                    raise ValueError("v2 subject shape drift")
                total = item["totalCourseCount"]
                ready = item["readyCourseCount"]
                formal_failed = item["failedCourseCount"]
                content_candidate = item["contentCandidateCount"]
                content_failed = item["contentFailedCount"]
                expected_total = int(
                    target["subjectTargets"][subject]["totalCourseCount"]
                )
                if not (
                    total == expected_total > 0
                    and ready >= 0
                    and formal_failed >= 0
                    and ready + formal_failed <= total
                    and content_candidate >= 0
                    and content_failed >= 0
                    and content_candidate + content_failed <= total
                ):
                    raise ValueError("v2 subject count drift")
                subject_totals["total"] += total
                subject_totals["ready"] += ready
                subject_totals["failed"] += formal_failed
                subject_totals["candidate"] += content_candidate
                subject_totals["content_failed"] += content_failed
            formal_root_keys = (
                "total_course_count",
                "ready_course_count",
                "failed_course_count",
            )
            if any(type(row.get(key)) is not int for key in formal_root_keys):
                raise ValueError("v2 formal count type drift")
            if not (
                subject_totals["total"] == row["total_course_count"] == target_count
                and subject_totals["ready"] == row["ready_course_count"]
                and subject_totals["failed"] == row["failed_course_count"]
                and subject_totals["candidate"] == candidate
                and subject_totals["content_failed"] == failed
            ):
                raise ValueError("v2 subject sum drift")
            if type(row.get("progress_percent")) is not int:
                raise ValueError("v2 progress type drift")
            status = str(row.get("status") or "")
            stage = str(row.get("stage") or "")
            content_progress_percent = max(
                LearningCurriculumPreparationRepository.STAGE_FLOORS[
                    "generating_content"
                ],
                5 + (30 * candidate // target_count),
            )
            if stage == "generating_content" and not (
                status == "running"
                and row["progress_percent"] == content_progress_percent
                and row.get("content_generation_completed_at") is None
                and row["ready_course_count"] == 0
                and row["failed_course_count"] == 0
            ):
                raise ValueError("v2 content stage state drift")
            inactive_work_fields = (
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
                "error_code",
                "error_message_safe",
            )
            if status == "ready":
                formal_count_fields = (
                    "classroom_ready_count",
                    "speech_ready_count",
                    "validation_ready_count",
                    "published_course_count",
                )
                formal_time_fields = (
                    "content_canary_passed_at",
                    "content_generation_completed_at",
                    "formal_ready_at",
                    "completed_at",
                )
                retry_ordinal = row.get("retry_ordinal")
                retry_of_plan_id = row.get("retry_of_plan_id")
                retry_identity_valid = type(retry_ordinal) is int and (
                    (retry_ordinal == 0 and retry_of_plan_id is None)
                    or (
                        retry_ordinal == 1
                        and isinstance(retry_of_plan_id, str)
                        and bool(retry_of_plan_id.strip())
                    )
                )
                receipt_hash = row.get("formal_publication_receipt_hash")
                if not (
                    stage == "completed"
                    and candidate == target_count == 30
                    and failed == 0
                    and row["progress_percent"] == 100
                    and row["ready_course_count"] == target_count
                    and row["failed_course_count"] == 0
                    and all(
                        type(row.get(key)) is int
                        and row[key] == target_count
                        for key in formal_count_fields
                    )
                    and all(
                        type(row.get(key)) is int and row[key] > 0
                        for key in formal_time_fields
                    )
                    and row["content_canary_passed_at"]
                    <= row["content_generation_completed_at"]
                    <= row["formal_ready_at"]
                    == row["completed_at"]
                    and str(row.get("preparation_contract_version") or "")
                    == str(target["preparationContractVersion"])
                    and isinstance(row.get("catalog_build_id"), str)
                    and bool(row["catalog_build_id"].strip())
                    and isinstance(row.get("catalog_release_id"), str)
                    and bool(row["catalog_release_id"].strip())
                    and str(row.get("formal_contract_version") or "")
                    == (
                        LearningCurriculumPreparationRepository
                        .FORMAL_PUBLICATION_CONTRACT_VERSION
                    )
                    and isinstance(
                        row.get("formal_publication_history_id"), str
                    )
                    and bool(row["formal_publication_history_id"].strip())
                    and isinstance(receipt_hash, str)
                    and re.fullmatch(r"[0-9a-f]{64}", receipt_hash) is not None
                    and row.get("superseded_at") is None
                    and retry_identity_valid
                    and all(row.get(key) is None for key in inactive_work_fields)
                ):
                    raise ValueError("v2 ready terminal state drift")
            elif candidate == target_count and failed == 0:
                handoff_null_fields = inactive_work_fields + (
                    "completed_at",
                    "superseded_at",
                )
                if not (
                    status == "running"
                    and stage == "building_classrooms"
                    and row["progress_percent"] == 35
                    and row["ready_course_count"] == 0
                    and row["failed_course_count"] == 0
                    and type(row.get("content_generation_completed_at")) is int
                    and all(row.get(key) is None for key in handoff_null_fields)
                ):
                    raise ValueError("v2 content handoff state drift")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ApiError(*PREPARATION_STATE_INVALID) from exc
        return subject_progress, {
            "candidateCount": candidate,
            "failedCount": failed,
            "targetCount": target_count,
            "canary": {
                "candidateCount": canary_candidate,
                "failedCount": canary_failed,
                "targetCount": canary_target,
                "passed": passed,
            },
        }

    @staticmethod
    def _negotiate_schema(
        *,
        header_present: bool,
        requested_schema: str | None,
    ) -> str:
        if not header_present:
            return PREPARATION_SCHEMA_VERSION
        if requested_schema == PREPARATION_SCHEMA_V2:
            return PREPARATION_SCHEMA_V2
        raise ApiError(*PREPARATION_SCHEMA_NOT_ACCEPTABLE)

    @staticmethod
    def _retry_after_ms(row: Mapping[str, object], *, now_ms: int) -> int | None:
        if str(row["status"]) not in {"queued", "running"}:
            return None
        last_progress_at = row.get("last_progress_at")
        if last_progress_at is None:
            return 30_000
        age = max(0, int(now_ms) - int(last_progress_at))
        for boundary, interval in (
            (5_000, 2_500),
            (15_000, 5_000),
            (30_000, 10_000),
            (60_000, 20_000),
        ):
            if age < boundary:
                return interval
        return 30_000

    @staticmethod
    def _parent_message(row: Mapping[str, object], *, grade_label: str) -> str:
        status = str(row["status"])
        if status == "ready":
            return f"{grade_label}今日课程已准备完成"
        if status == "failed":
            return "系统正在后台恢复今日课程"
        if status == "superseded":
            return "已切换年级，旧课程准备计划已停止"
        return "系统正在后台准备今日课程"

    @staticmethod
    def _public_safe_error(
        row: Mapping[str, object],
    ) -> dict[str, str] | None:
        if not row.get("error_code"):
            return None
        code = str(row["error_code"])
        message = PUBLIC_ERROR_MESSAGES.get(code)
        if message is None:
            return dict(GENERIC_PUBLIC_ERROR)
        return {"code": code, "message": message}
