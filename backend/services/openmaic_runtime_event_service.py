from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from typing import Any, Callable, Mapping

from core.errors import ApiError
from core.security import now_ms
from integrations.openmaic_formal_interaction import validate_interaction_manifest
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from services.formal_student_learning_access import (
    formal_course_count,
    FORMAL_PUBLICATION_CONTRACT_VERSION,
    assert_formal_student_grade_open,
)


RUNTIME_EVENT_SCHEMA = "mira.openmaic.student-runtime-event.v1"
RUNTIME_EVENT_RECEIPT_SCHEMA = "mira.openmaic.student-runtime-event-receipt.v1"
_EVENT_TYPES = frozenset(
    {
        "scene_entered",
        "action_completed",
        "answer_submitted",
        "asr_transcribed",
        "interaction_completed",
        "classroom_completed",
    }
)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_PAYLOAD_FIELDS = {
    "scene_entered": frozenset({"sceneIndex", "sceneId"}),
    "action_completed": frozenset({"sceneIndex", "sceneId", "actionId"}),
    "answer_submitted": frozenset(
        {"sceneIndex", "sceneId", "questionId", "response", "attemptNumber"}
    ),
    "asr_transcribed": frozenset(
        {"sceneIndex", "sceneId", "turnId", "transcript"}
    ),
    "interaction_completed": frozenset({"sceneIndex", "sceneId", "objectiveIndex", "controlSelector", "action", "value", "feedbackText"}),
    "classroom_completed": frozenset({"sceneIndex", "sceneId"}),
}

logger = logging.getLogger(__name__)


class OpenMaicRuntimeEventService:
    """Consume one authenticated, session-bound Runtime event stream.

    The browser supplies only classroom activity. Identity comes from the
    trusted gateway and scoring comes from ``LearningService``. One database
    transaction owns sequence validation, authoritative learning mutations,
    the durable event receipt, and final report publication.
    """

    def __init__(
        self,
        *,
        repository: Any,
        learning_service: Any,
        task_runtime_service: Any | None = None,
        budget_service: Any | None = None,
        teaching_conversation_reader: Any | None = None,
        clock: Callable[[], int] = now_ms,
    ):
        self.repository = repository
        self.learning_service = learning_service
        self.task_runtime_service = task_runtime_service
        self.budget_service = budget_service
        self.teaching_conversation_reader = teaching_conversation_reader
        self.clock = clock

    def status(
        self,
        *,
        runtime_session_id: str,
        learning_session_id: str,
        upstream_classroom_id: str,
    ) -> dict[str, Any]:
        trusted_runtime_id = self._identifier(
            runtime_session_id, "runtimeSessionId", maximum=128
        )
        trusted_learning_id = self._identifier(
            learning_session_id, "learningSessionId", maximum=255
        )
        trusted_classroom_id = self._identifier(
            upstream_classroom_id, "classroomId", maximum=255
        )
        timestamp = self.clock()
        with self.repository.transaction() as conn:
            authority = self.repository.get_runtime_authority(
                conn,
                runtime_session_id=trusted_runtime_id,
                learning_session_id=trusted_learning_id,
                upstream_classroom_id=trusted_classroom_id,
                for_update=True,
            )
            if authority is None:
                raise ApiError(
                    "runtime_event_session_not_found",
                    "课堂会话不存在或身份不匹配",
                    404,
                )
            expected_scenes = self._validate_authority(
                authority,
                runtime_session_id=trusted_runtime_id,
                learning_session_id=trusted_learning_id,
                upstream_classroom_id=trusted_classroom_id,
                now=timestamp,
            )
            expected_scene_count = len(expected_scenes)
            stream = self.repository.get_stream(
                conn,
                runtime_session_id=trusted_runtime_id,
                for_update=False,
            )
            evidence = self._authoritative_scene_evidence(
                conn,
                authority=authority,
            )
            answered_question_ids = [
                self._identifier(question_id, "questionId", maximum=128)
                for question_id in self.learning_service.authoritative_runtime_answered_question_ids(
                    conn,
                    authority=authority,
                )
            ]
            questions_complete = bool(
                self.learning_service.authoritative_runtime_questions_complete(
                    conn,
                    authority=authority,
                )
            )
            if stream is not None:
                self._validate_stream(
                    stream,
                    authority=authority,
                    expected_scene_count=expected_scene_count,
                )
            last_sequence = int((stream or {}).get("last_sequence") or 0)
            completed = (stream or {}).get("completed_at") is not None
            scene_count = int(evidence.get("scene_count") or 0)
            action_scene_count = int(evidence.get("action_scene_count") or 0)
            interaction_objectives = self._interaction_objectives(authority)
            interaction_evidence = self._interaction_evidence(conn, authority=authority) if interaction_objectives else []
            completed_interactions = self._completed_interactions(interaction_objectives, interaction_evidence)
            completion_ready = bool(
                not completed
                and scene_count == expected_scene_count
                and action_scene_count == expected_scene_count
                and int(evidence.get("maximum_scene_index") or -1)
                == expected_scene_count - 1
                and questions_complete
                and len(completed_interactions) == len(interaction_objectives)
            )
            response = {
                "ok": True,
                "schemaVersion": RUNTIME_EVENT_RECEIPT_SCHEMA,
                "runtimeSessionId": trusted_runtime_id,
                "learningSessionId": trusted_learning_id,
                "classroomId": trusted_classroom_id,
                "releaseId": str(authority["candidate_release_id"]),
                "lastSequence": last_sequence,
                "nextSequence": last_sequence + 1,
                "completed": completed,
                "reportId": (stream or {}).get("report_id"),
                "expectedSceneCount": expected_scene_count,
                "sceneEnteredCount": scene_count,
                "actionCompletedSceneCount": action_scene_count,
                "questionsComplete": questions_complete,
                "answeredQuestionIds": answered_question_ids,
                "completionReady": completion_ready,
                "completedInteractionObjectiveIndexes": sorted(completed_interactions),
                "completedActionSceneIds": self.repository.learning_session_completed_action_scene_ids(
                    conn, family_id=str(authority["family_id"]), child_id=str(authority["child_id"]),
                    learning_session_id=str(authority["learning_session_id"]),
                    runtime_classroom_id=str(authority["runtime_classroom_id"]),
                    release_id=str(authority["candidate_release_id"]),
                    target_fingerprint=str(authority["candidate_target_fingerprint"]),
                ),
            }
        if completed:
            self._close_completed_budget(authority)
        return response

    def record(
        self,
        *,
        runtime_session_id: str,
        learning_session_id: str,
        upstream_classroom_id: str,
        data: Mapping[str, Any],
    ) -> dict[str, Any]:
        trusted_runtime_id = self._identifier(
            runtime_session_id, "runtimeSessionId", maximum=128
        )
        trusted_learning_id = self._identifier(
            learning_session_id, "learningSessionId", maximum=255
        )
        trusted_classroom_id = self._identifier(
            upstream_classroom_id, "classroomId", maximum=255
        )
        event = self._event(data)
        expected_key = self.idempotency_key(
            runtime_session_id=trusted_runtime_id,
            event=event,
        )
        if not hmac.compare_digest(expected_key, event["idempotencyKey"]):
            raise ApiError(
                "runtime_event_idempotency_invalid",
                "课堂事件幂等标识无效",
                409,
            )
        request_sha256 = self._sha256(event)
        timestamp = self.clock()
        follow_up: tuple[str, str, str] | None = None

        with self.repository.transaction() as conn:
            authority = self._lock_current_formal_authority(
                conn,
                runtime_session_id=trusted_runtime_id,
                learning_session_id=trusted_learning_id,
                upstream_classroom_id=trusted_classroom_id,
            )
            expected_scenes = self._validate_authority(
                authority,
                runtime_session_id=trusted_runtime_id,
                learning_session_id=trusted_learning_id,
                upstream_classroom_id=trusted_classroom_id,
                now=timestamp,
            )
            expected_scene_count = len(expected_scenes)
            stream = self.repository.create_or_get_stream(
                conn,
                authority=authority,
                now=timestamp,
            )
            self._validate_stream(
                stream,
                authority=authority,
                expected_scene_count=expected_scene_count,
            )

            prior = self.repository.get_event_by_idempotency(
                conn,
                runtime_session_id=trusted_runtime_id,
                idempotency_key=event["idempotencyKey"],
            )
            if prior is not None:
                if (
                    int(prior.get("sequence") or 0) != event["sequence"]
                    or str(prior.get("event_type") or "") != event["type"]
                    or str(prior.get("request_sha256") or "") != request_sha256
                ):
                    raise ApiError(
                        "runtime_event_idempotency_conflict",
                        "课堂事件幂等标识已用于另一条事件",
                        409,
                    )
                response = self.repository.decode_response(prior)
                if not isinstance(response, dict):
                    raise ApiError(
                        "runtime_event_receipt_invalid",
                        "课堂事件回执不可用",
                        503,
                    )
                return response

            if stream.get("completed_at") is not None:
                raise ApiError(
                    "runtime_event_stream_completed",
                    "本次完整课堂已经完成",
                    409,
                )

            same_sequence = self.repository.get_event_by_sequence(
                conn,
                runtime_session_id=trusted_runtime_id,
                sequence=event["sequence"],
            )
            if same_sequence is not None:
                raise ApiError(
                    "runtime_event_sequence_conflict",
                    "课堂事件序号已用于另一条事件",
                    409,
                )
            last_sequence = int(stream.get("last_sequence") or 0)
            if event["sequence"] <= last_sequence:
                raise ApiError(
                    "runtime_event_sequence_stale",
                    "课堂事件序号已经过期",
                    409,
                )
            if event["sequence"] != last_sequence + 1:
                raise ApiError(
                    "runtime_event_sequence_gap",
                    "课堂事件序号不连续，请先同步进度",
                    409,
                )

            self._validate_scene_transition(
                conn,
                stream=stream,
                event=event,
                expected_scenes=expected_scenes,
            )
            objectives = self._interaction_objectives(authority)
            if event["type"] == "interaction_completed":
                matched = next((item for item in objectives if item["objectiveIndex"] == event["payload"]["objectiveIndex"]), None)
                if matched is None or not self._operation_matches(matched, event["payload"]):
                    raise ApiError("runtime_event_interaction_authority_mismatch", "操作结果与已发布课程不一致", 409)
            elif event["type"] == "answer_submitted" and objectives:
                required = {item["objectiveIndex"] for item in objectives if item["independentJudgment"]["questionId"] == event["payload"]["questionId"]}
                completed_operations = self._completed_interactions(objectives, self._interaction_evidence(conn, authority=authority))
                if not required.issubset(completed_operations):
                    raise ApiError("runtime_event_interaction_incomplete", "请先完成动手探索，再独立作答", 409)
            authoritative: dict[str, Any] | None = None
            report_id: str | None = None
            completed = False
            if event["type"] in {"action_completed", "classroom_completed"}:
                self._require_teaching_completed(authority,
                    scene_id=event["payload"]["sceneId"] if event["type"] == "action_completed" else None)
            if event["type"] == "answer_submitted":
                authoritative = self.learning_service.record_authoritative_runtime_answer(
                    conn,
                    authority=authority,
                    question_id=event["payload"]["questionId"],
                    submitted_answer=event["payload"]["response"],
                    attempt_number=event["payload"]["attemptNumber"],
                    now=timestamp,
                )
            elif event["type"] == "classroom_completed":
                self._require_completion_evidence(
                    conn,
                    authority=authority,
                    expected_scene_count=expected_scene_count,
                )
                report = self.learning_service.complete_authoritative_runtime_session(
                    conn,
                    authority=authority,
                    now=timestamp,
                )
                report_id = str(report.get("id") or "")
                if not report_id:
                    raise ApiError(
                        "runtime_event_report_invalid",
                        "学习报告未能安全生成",
                        503,
                    )
                completed = True

            response = {
                "ok": True,
                "schemaVersion": RUNTIME_EVENT_RECEIPT_SCHEMA,
                "runtimeSessionId": trusted_runtime_id,
                "learningSessionId": trusted_learning_id,
                "classroomId": trusted_classroom_id,
                "releaseId": str(authority["candidate_release_id"]),
                "sequence": event["sequence"],
                "type": event["type"],
                "completed": completed,
                "reportId": report_id,
                "authoritativeEvaluation": authoritative,
            }
            response["receiptSha256"] = self._sha256(response)
            self.repository.append_event(
                conn,
                stream=stream,
                event=event,
                request_sha256=request_sha256,
                authoritative=authoritative,
                response=response,
                now=timestamp,
            )
            if event["type"] == "scene_entered":
                follow_up = (
                    "started",
                    str(authority["family_id"]),
                    str(authority["session_task_id"]),
                )
            elif event["type"] == "classroom_completed":
                follow_up = (
                    "completed",
                    str(authority["family_id"]),
                    str(authority["session_task_id"]),
                )

        self._coordinate_task_runtime(follow_up)
        if completed:
            self._close_completed_budget(authority)
        return response

    def _require_teaching_completed(self, authority, *, scene_id=None):
        from services.learning_paid_authority import scope_digest, teaching_budget_scope, upgraded_manifest
        from services.openmaic_paid_call_service import teaching_conversation_id
        manifest = authority.get("feature_manifest_json")
        manifest = json.loads(manifest) if isinstance(manifest, str) else manifest
        if not isinstance(manifest, Mapping) or not upgraded_manifest(manifest):
            return
        actions = manifest["formalEvidence"]["requiredTeachingActions"]
        required = [item for item in actions if scene_id is None or item["sceneId"] == scene_id]
        if not required:
            return
        if getattr(self, "teaching_conversation_reader", None) is None:
            raise ApiError("runtime_teaching_verification_unavailable", "老师指导的完成记录暂时无法确认，进度已保留。", 503)
        row = {**authority, "course_id": authority["session_course_id"], "course_version": authority["session_course_version"]}
        identity = scope_digest(teaching_budget_scope(row, manifest, "required_teaching"))
        for action in required:
            conversation_id = teaching_conversation_id(authorization_id=identity,
                learning_session_id=authority["learning_session_id"], classroom_id=authority["upstream_classroom_id"],
                scene_id=action["sceneId"], action_id=action["actionId"])
            try:
                conversation = self.teaching_conversation_reader(conversation_id=conversation_id,
                    learning_session_id=authority["learning_session_id"], classroom_id=authority["upstream_classroom_id"])
            except OpenMaicFullRuntimeError as exc:
                raise ApiError("runtime_teaching_verification_unavailable", "老师指导的完成记录暂时无法确认，进度已保留。", 503) from exc
            if (not isinstance(conversation, Mapping) or conversation.get("id") != conversation_id
                    or conversation.get("authorizationId") != identity or conversation.get("state") != "completed"):
                raise ApiError("runtime_teaching_incomplete", "这段老师指导尚未完成，请先继续课堂对话。", 409)

    def _close_completed_budget(self, authority: Mapping[str, Any]) -> None:
        # Budget uses its own lock order. Always run after learning commits; a
        # budget outage must never undo the child's completed work/report.
        if self.budget_service is None:
            return
        from services.learning_paid_authority import scope_digest, teaching_budget_scope, upgraded_manifest
        manifest = authority.get("feature_manifest_json")
        try:
            manifest = json.loads(manifest) if isinstance(manifest, str) else manifest
            if not isinstance(manifest, Mapping) or not upgraded_manifest(manifest):
                return
            row = {**authority, "course_id": authority["session_course_id"],
                   "course_version": authority["session_course_version"]}
            for purpose in ("required_teaching", "optional_interaction"):
                try:
                    self.budget_service.close_authorization(authorization_id=scope_digest(teaching_budget_scope(row, manifest, purpose)))
                except ApiError as exc:
                    if exc.status_code != 404:
                        logger.warning("Budget close will retry on completed session status: %s", authority["learning_session_id"])
        except Exception:
            logger.exception("Could not close completed learning budget: %s", authority.get("learning_session_id"))

    def _coordinate_task_runtime(
        self,
        follow_up: tuple[str, str, str] | None,
    ) -> None:
        """Run camera/reminder cleanup only after the event transaction commits."""

        if follow_up is None or self.task_runtime_service is None:
            return
        event_name, family_id, task_id = follow_up
        try:
            if event_name == "completed":
                self.task_runtime_service.learning_classroom_completed(
                    family_id=family_id,
                    task_id=task_id,
                )
            else:
                self.task_runtime_service.learning_classroom_started(
                    family_id=family_id,
                    task_id=task_id,
                )
        except Exception:
            # The committed Runtime receipt remains authoritative. Camera and
            # reminder coordination is a best-effort side effect and must never
            # make the browser resend a valid event.
            logger.exception(
                "OpenMAIC task-runtime coordination failed for task %s",
                task_id,
            )

    def _lock_current_formal_authority(
        self,
        conn: Any,
        *,
        runtime_session_id: str,
        learning_session_id: str,
        upstream_classroom_id: str,
    ) -> Mapping[str, Any]:
        """Acquire the write authority in the system-wide lock order.

        The first query is deliberately an unlocked key snapshot.  It cannot
        authorize a write: every discovered identity is compared with rows
        locked in child -> task/session -> formal publication -> Runtime order.
        This lets a concurrent grade/profile change either commit first and be
        observed here, or wait until this event transaction commits.
        """

        subject = self.repository.get_runtime_subject(
            conn,
            runtime_session_id=runtime_session_id,
            learning_session_id=learning_session_id,
            upstream_classroom_id=upstream_classroom_id,
        )
        if subject is None:
            raise self._session_not_found()

        family_id = str(subject.get("family_id") or "")
        child_id = str(subject.get("child_id") or "")
        principal_id = str(subject.get("principal_id") or "")
        task_id = str(subject.get("task_id") or "")
        course_id = str(subject.get("course_id") or "")
        course_version = str(subject.get("course_version") or "")
        package_id = str(subject.get("package_id") or "")
        package_version = self._positive_integer(subject.get("package_version"))
        if not all(
            (
                family_id,
                child_id,
                principal_id,
                task_id,
                course_id,
                course_version,
                package_id,
                package_version,
            )
        ):
            raise self._session_not_found()

        child = self.repository.get_child_for_update(
            conn,
            family_id=family_id,
            child_id=child_id,
        )
        if child is None or any(
            str(child.get(key) or "") != expected
            for key, expected in (("id", child_id), ("family_id", family_id))
        ):
            raise self._session_not_found()
        grade_code = assert_formal_student_grade_open(child)
        grade_revision = self._positive_integer(
            child.get("grade_selection_revision")
        )
        if grade_revision < 1:
            raise self._release_not_ready()
        # A new, supported grade must still invalidate the former grade's
        # frozen classroom. This unlocked snapshot is only an early rejection;
        # matching identities remain subject to the locked authority checks.
        if subject.get("binding_grade_code") and (
            str(subject["binding_grade_code"]) != grade_code
            or self._positive_integer(subject.get("binding_grade_revision")) != grade_revision
        ):
            raise self._release_not_ready()

        principal = self.repository.get_principal_for_update(
            conn,
            principal_id=principal_id,
        )
        if principal is None or any(
            str(principal.get(key) or "") != expected
            for key, expected in (
                ("id", principal_id),
                ("family_id", family_id),
                ("child_id", child_id),
                ("status", "active"),
            )
        ):
            raise self._session_not_found()

        task = self.repository.get_task_for_update(
            conn,
            family_id=family_id,
            task_id=task_id,
        )
        session = self.repository.get_learning_session_for_update(
            conn,
            family_id=family_id,
            learning_session_id=learning_session_id,
        )
        if not self._task_session_matches(
            task=task,
            session=session,
            family_id=family_id,
            child_id=child_id,
            task_id=task_id,
            learning_session_id=learning_session_id,
            course_id=course_id,
            course_version=course_version,
            package_id=package_id,
            package_version=package_version,
        ):
            raise self._release_not_ready()

        if str(subject.get("binding_authority_kind") or "") in {
            "active_pointer",
            "progressive_plan",
        }:
            return self._lock_immutable_formal_binding_authority(
                conn,
                subject=subject,
                child=child,
                grade_code=grade_code,
                runtime_session_id=runtime_session_id,
                learning_session_id=learning_session_id,
                upstream_classroom_id=upstream_classroom_id,
                course_id=course_id,
                course_version=course_version,
                package_id=package_id,
                package_version=package_version,
            )

        pointer = self.repository.get_formal_pointer_for_update(
            conn,
            grade_code=grade_code,
        )
        if not self._pointer_ready(pointer, grade_code=grade_code):
            raise self._release_not_ready()
        assert pointer is not None

        plan = self.repository.get_formal_plan_for_update(
            conn,
            family_id=family_id,
            child_id=child_id,
            grade_code=grade_code,
            grade_selection_revision=grade_revision,
        )
        if not self._plan_matches_current_release(
            plan,
            family_id=family_id,
            child_id=child_id,
            grade_code=grade_code,
            grade_revision=grade_revision,
            pointer=pointer,
        ):
            raise self._release_not_ready()
        assert plan is not None

        history_id = str(pointer.get("history_id") or "")
        history = self.repository.get_formal_history_for_update(
            conn,
            history_id=history_id,
            grade_code=grade_code,
        )
        if not self._history_matches_current_release(
            history,
            pointer=pointer,
            publication_receipt_hash=str(
                plan.get("formal_publication_receipt_hash") or ""
            ),
        ):
            raise self._release_not_ready()

        ownership = self.repository.get_formal_course_ownership_for_update(
            conn,
            learning_session_id=learning_session_id,
            release_id=str(pointer["release_id"]),
            grade_code=grade_code,
            course_id=course_id,
            course_version=course_version,
            package_id=package_id,
            package_version=package_version,
        )
        if not self._course_owned_by_current_release(
            ownership,
            pointer=pointer,
            grade_code=grade_code,
            course_id=course_id,
            course_version=course_version,
            package_id=package_id,
            package_version=package_version,
            runtime_classroom_id=str(subject.get("runtime_classroom_id") or ""),
            upstream_classroom_id=upstream_classroom_id,
        ):
            raise self._release_not_ready()
        assert ownership is not None

        authority = self.repository.get_runtime_authority(
            conn,
            runtime_session_id=runtime_session_id,
            learning_session_id=learning_session_id,
            upstream_classroom_id=upstream_classroom_id,
            for_update=True,
        )
        if authority is None:
            raise self._session_not_found()
        if not self._runtime_matches_locked_authority(
            authority,
            subject=subject,
            pointer=pointer,
            ownership=ownership,
            grade_code=grade_code,
        ):
            raise self._release_not_ready()
        return authority

    def _lock_immutable_formal_binding_authority(
        self,
        conn: Any,
        *,
        subject: Mapping[str, Any],
        child: Mapping[str, Any],
        grade_code: str,
        runtime_session_id: str,
        learning_session_id: str,
        upstream_classroom_id: str,
        course_id: str,
        course_version: str,
        package_id: str,
        package_version: int,
    ) -> Mapping[str, Any]:
        """Lock and verify the release authority frozen when the session began."""

        ownership = self.repository.get_formal_course_ownership_for_update(
            conn,
            learning_session_id=learning_session_id,
            release_id=str(subject.get("binding_release_id") or ""),
            grade_code=grade_code,
            course_id=course_id,
            course_version=course_version,
            package_id=package_id,
            package_version=package_version,
        )
        if not self._course_owned_by_immutable_binding(
            ownership,
            subject=subject,
            child=child,
            grade_code=grade_code,
            course_id=course_id,
            course_version=course_version,
            package_id=package_id,
            package_version=package_version,
            runtime_classroom_id=str(subject.get("runtime_classroom_id") or ""),
            upstream_classroom_id=upstream_classroom_id,
        ):
            raise self._release_not_ready()
        assert ownership is not None

        authority = self.repository.get_runtime_authority(
            conn,
            runtime_session_id=runtime_session_id,
            learning_session_id=learning_session_id,
            upstream_classroom_id=upstream_classroom_id,
            for_update=True,
        )
        if authority is None:
            raise self._session_not_found()
        if not self._runtime_matches_immutable_binding(
            authority,
            subject=subject,
            ownership=ownership,
            grade_code=grade_code,
        ):
            raise self._release_not_ready()
        return authority

    @classmethod
    def _task_session_matches(
        cls,
        *,
        task: Mapping[str, Any] | None,
        session: Mapping[str, Any] | None,
        family_id: str,
        child_id: str,
        task_id: str,
        learning_session_id: str,
        course_id: str,
        course_version: str,
        package_id: str,
        package_version: int,
    ) -> bool:
        if task is None or session is None:
            return False
        expected_task = {
            "id": task_id,
            "family_id": family_id,
            "child_id": child_id,
            "type": "learning",
            "learning_course_id": course_id,
            "learning_course_version": course_version,
        }
        expected_session = {
            "id": learning_session_id,
            "family_id": family_id,
            "child_id": child_id,
            "task_id": task_id,
            "course_id": course_id,
            "course_version": course_version,
            "lesson_package_id": package_id,
        }
        return (
            all(str(task.get(key) or "") == value for key, value in expected_task.items())
            and all(
                str(session.get(key) or "") == value
                for key, value in expected_session.items()
            )
            and cls._positive_integer(session.get("lesson_package_version"))
            == package_version
        )

    @classmethod
    def _pointer_ready(
        cls,
        pointer: Mapping[str, Any] | None,
        *,
        grade_code: str,
    ) -> bool:
        return bool(
            pointer is not None
            and str(pointer.get("grade_code") or "") == grade_code
            and cls._positive_integer(pointer.get("pointer_revision")) >= 1
            and cls._sha256_text(pointer.get("target_fingerprint"))
            and str(pointer.get("contract_version") or "")
            == FORMAL_PUBLICATION_CONTRACT_VERSION
            and str(pointer.get("release_id") or "")
            and str(pointer.get("history_id") or "")
            and cls._positive_integer(pointer.get("activated_at")) > 0
        )

    @classmethod
    def _plan_matches_current_release(
        cls,
        plan: Mapping[str, Any] | None,
        *,
        family_id: str,
        child_id: str,
        grade_code: str,
        grade_revision: int,
        pointer: Mapping[str, Any],
    ) -> bool:
        if plan is None:
            return False
        total = cls._positive_integer(plan.get("total_course_count"))
        return bool(
            str(plan.get("family_id") or "") == family_id
            and str(plan.get("child_id") or "") == child_id
            and str(plan.get("grade_code") or "") == grade_code
            and cls._positive_integer(plan.get("grade_selection_revision"))
            == grade_revision
            and str(plan.get("status") or "") == "ready"
            and str(plan.get("stage") or "") == "completed"
            and plan.get("superseded_at") is None
            and cls._positive_integer(plan.get("progress_percent")) == 100
            and total == formal_course_count(grade_code)
            and cls._positive_integer(plan.get("ready_course_count")) == total
            and cls._positive_integer(plan.get("failed_course_count")) == 0
            and cls._positive_integer(plan.get("content_target_count")) == total
            and cls._positive_integer(plan.get("content_candidate_count")) == total
            and cls._positive_integer(plan.get("content_failed_count")) == 0
            and cls._positive_integer(plan.get("classroom_ready_count")) == total
            and cls._positive_integer(plan.get("speech_ready_count")) == total
            and cls._positive_integer(plan.get("validation_ready_count")) == total
            and cls._positive_integer(plan.get("published_course_count")) == total
            and cls._positive_integer(plan.get("formal_ready_at")) > 0
            and cls._positive_integer(plan.get("completed_at")) > 0
            and str(plan.get("catalog_release_id") or "")
            == str(pointer.get("release_id") or "")
            and str(plan.get("target_fingerprint") or "")
            == str(pointer.get("target_fingerprint") or "")
            and str(plan.get("formal_contract_version") or "")
            == str(pointer.get("contract_version") or "")
            and str(plan.get("formal_publication_history_id") or "")
            == str(pointer.get("history_id") or "")
            and cls._sha256_text(plan.get("formal_publication_receipt_hash"))
        )

    @classmethod
    def _history_matches_current_release(
        cls,
        history: Mapping[str, Any] | None,
        *,
        pointer: Mapping[str, Any],
        publication_receipt_hash: str,
    ) -> bool:
        if history is None:
            return False
        return bool(
            str(history.get("id") or "") == str(pointer.get("history_id") or "")
            and str(history.get("grade_code") or "")
            == str(pointer.get("grade_code") or "")
            and cls._positive_integer(history.get("pointer_revision"))
            == cls._positive_integer(pointer.get("pointer_revision"))
            and str(history.get("target_fingerprint") or "")
            == str(pointer.get("target_fingerprint") or "")
            and str(history.get("contract_version") or "")
            == str(pointer.get("contract_version") or "")
            and str(history.get("release_id") or "")
            == str(pointer.get("release_id") or "")
            and str(history.get("activation_source") or "")
            == "formal_publication"
            and str(history.get("publication_receipt_hash") or "")
            == publication_receipt_hash
            and history.get("superseded_at") is None
        )

    @classmethod
    def _course_owned_by_current_release(
        cls,
        ownership: Mapping[str, Any] | None,
        *,
        pointer: Mapping[str, Any],
        grade_code: str,
        course_id: str,
        course_version: str,
        package_id: str,
        package_version: int,
        runtime_classroom_id: str,
        upstream_classroom_id: str,
    ) -> bool:
        if ownership is None:
            return False
        expected = {
            "release_id": str(pointer.get("release_id") or ""),
            "grade_code": grade_code,
            "course_id": course_id,
            "course_version": course_version,
            "package_id": package_id,
            "binding_history_id": str(pointer.get("history_id") or ""),
            "binding_target_fingerprint": str(
                pointer.get("target_fingerprint") or ""
            ),
            "binding_contract_version": FORMAL_PUBLICATION_CONTRACT_VERSION,
            "runtime_classroom_id": runtime_classroom_id,
            "upstream_classroom_id": upstream_classroom_id,
            "release_status": "published",
            "release_quality_status": "ready",
            "release_item_status": "published",
            "release_item_quality_status": "ready",
        }
        return bool(
            all(
                str(ownership.get(key) or "") == value
                for key, value in expected.items()
            )
            and cls._positive_integer(ownership.get("package_version"))
            == package_version
            and cls._positive_integer(ownership.get("binding_pointer_revision"))
            == cls._positive_integer(pointer.get("pointer_revision"))
            and cls._positive_integer(ownership.get("release_ready_item_count"))
            == formal_course_count(grade_code)
            and cls._positive_integer(ownership.get("release_activated_at")) > 0
            and ownership.get("release_retired_at") is None
            and ownership.get("release_item_retired_at") is None
            and str(ownership.get("build_item_id") or "")
        )

    @classmethod
    def _course_owned_by_immutable_binding(
        cls,
        ownership: Mapping[str, Any] | None,
        *,
        subject: Mapping[str, Any],
        child: Mapping[str, Any],
        grade_code: str,
        course_id: str,
        course_version: str,
        package_id: str,
        package_version: int,
        runtime_classroom_id: str,
        upstream_classroom_id: str,
    ) -> bool:
        if ownership is None:
            return False
        authority_kind = str(subject.get("binding_authority_kind") or "")
        target_fingerprint = str(
            subject.get("binding_target_fingerprint") or ""
        )
        expected = {
            "release_id": str(subject.get("binding_release_id") or ""),
            "grade_code": grade_code,
            "course_id": course_id,
            "course_version": course_version,
            "package_id": package_id,
            "binding_authority_kind": authority_kind,
            "build_item_id": str(subject.get("binding_build_item_id") or ""),
            "binding_target_fingerprint": target_fingerprint,
            "binding_contract_version": FORMAL_PUBLICATION_CONTRACT_VERSION,
            "binding_runtime_contract_version": (
                "mira.learning.candidate-runtime-binding.v1"
            ),
            "binding_package_content_hash": str(
                subject.get("binding_package_content_hash") or ""
            ),
            "runtime_classroom_id": runtime_classroom_id,
            "upstream_classroom_id": upstream_classroom_id,
            "release_item_status": "published",
            "release_item_quality_status": "ready",
        }
        build_item_ready = bool(
            ownership.get("build_item_status") == "ready"
            or (
                ownership.get("build_item_status") == "course_ready"
                and ownership.get("build_item_execution_mode_snapshot")
                == "content_only"
                and ownership.get("build_item_content_phase") == "course_ready"
                and ownership.get("build_item_content_gate_status") == "passed"
                and ownership.get("build_item_content_gate_passed_at") is not None
                and str(
                    ownership.get("build_item_content_validation_contract_version")
                    or ""
                )
                and cls._sha256_text(ownership.get("build_item_content_receipt_hash"))
            )
        )
        common_valid = bool(
            all(
                str(ownership.get(key) or "") == value
                for key, value in expected.items()
            )
            and build_item_ready
            and cls._positive_integer(ownership.get("package_version"))
            == package_version
            and cls._positive_integer(subject.get("binding_package_version"))
            == package_version
            and str(subject.get("binding_course_id") or "") == course_id
            and str(subject.get("binding_course_version") or "")
            == course_version
            and str(subject.get("binding_package_id") or "") == package_id
            and str(subject.get("package_content_hash") or "")
            == str(subject.get("binding_package_content_hash") or "")
            and cls._sha256_text(target_fingerprint)
            and cls._sha256_text(subject.get("binding_package_content_hash"))
            and ownership.get("release_retired_at") is None
            and ownership.get("release_item_retired_at") is None
        )
        if not common_valid:
            return False

        if authority_kind == "active_pointer":
            history_id = str(subject.get("binding_history_id") or "")
            pointer_revision = cls._positive_integer(
                subject.get("binding_pointer_revision")
            )
            return bool(
                history_id
                and pointer_revision >= 1
                and not str(subject.get("binding_plan_id") or "")
                and cls._positive_integer(subject.get("binding_grade_revision")) == 0
                and str(ownership.get("binding_history_id") or "") == history_id
                and cls._positive_integer(
                    ownership.get("binding_pointer_revision")
                )
                == pointer_revision
                and str(ownership.get("authority_history_id") or "")
                == history_id
                and str(ownership.get("authority_history_grade_code") or "")
                == grade_code
                and cls._positive_integer(
                    ownership.get("authority_history_revision")
                )
                == pointer_revision
                and str(ownership.get("authority_history_fingerprint") or "")
                == target_fingerprint
                and str(
                    ownership.get("authority_history_contract_version") or ""
                )
                == FORMAL_PUBLICATION_CONTRACT_VERSION
                and str(ownership.get("authority_history_release_id") or "")
                == str(subject.get("binding_release_id") or "")
                and str(
                    ownership.get("authority_history_activation_source") or ""
                )
                == "formal_publication"
            )

        binding_grade_revision = cls._positive_integer(
            subject.get("binding_grade_revision")
        )
        return bool(
            authority_kind == "progressive_plan"
            and not str(subject.get("binding_history_id") or "")
            and cls._positive_integer(subject.get("binding_pointer_revision")) == 0
            and str(subject.get("binding_plan_id") or "")
            and binding_grade_revision >= 1
            and binding_grade_revision
            == cls._positive_integer(child.get("grade_selection_revision"))
            and str(ownership.get("binding_plan_id") or "")
            == str(subject.get("binding_plan_id") or "")
            and cls._positive_integer(ownership.get("binding_grade_revision"))
            == binding_grade_revision
            and str(ownership.get("authority_plan_id") or "")
            == str(subject.get("binding_plan_id") or "")
            and str(ownership.get("authority_plan_family_id") or "")
            == str(subject.get("family_id") or "")
            and str(ownership.get("authority_plan_child_id") or "")
            == str(subject.get("child_id") or "")
            and str(ownership.get("authority_plan_grade_code") or "")
            == grade_code
            and cls._positive_integer(
                ownership.get("authority_plan_grade_revision")
            )
            == binding_grade_revision
            and str(ownership.get("authority_plan_build_id") or "")
            == str(ownership.get("build_job_id") or "")
            and str(ownership.get("authority_plan_release_id") or "")
            == str(subject.get("binding_release_id") or "")
            and str(ownership.get("authority_plan_fingerprint") or "")
            == target_fingerprint
            and str(ownership.get("authority_plan_status") or "")
            in {"queued", "running", "ready", "failed"}
        )

    @classmethod
    def _runtime_matches_immutable_binding(
        cls,
        authority: Mapping[str, Any],
        *,
        subject: Mapping[str, Any],
        ownership: Mapping[str, Any],
        grade_code: str,
    ) -> bool:
        expected = {
            "runtime_session_id": str(subject.get("runtime_session_id") or ""),
            "principal_id": str(subject.get("principal_id") or ""),
            "family_id": str(subject.get("family_id") or ""),
            "child_id": str(subject.get("child_id") or ""),
            "learning_session_id": str(subject.get("learning_session_id") or ""),
            "runtime_classroom_id": str(subject.get("runtime_classroom_id") or ""),
            "upstream_classroom_id": str(subject.get("upstream_classroom_id") or ""),
            "session_task_id": str(subject.get("task_id") or ""),
            "session_course_id": str(subject.get("course_id") or ""),
            "session_course_version": str(subject.get("course_version") or ""),
            "session_package_id": str(subject.get("package_id") or ""),
            "candidate_grade_code": grade_code,
            "course_grade_code": grade_code,
            "candidate_release_id": str(subject.get("binding_release_id") or ""),
            "candidate_target_fingerprint": str(
                subject.get("binding_target_fingerprint") or ""
            ),
            "candidate_build_item_id": str(
                subject.get("binding_build_item_id") or ""
            ),
        }
        return bool(
            all(
                str(authority.get(key) or "") == value
                for key, value in expected.items()
            )
            and cls._positive_integer(authority.get("session_package_version"))
            == cls._positive_integer(subject.get("package_version"))
            and str(ownership.get("build_item_id") or "")
            == str(subject.get("binding_build_item_id") or "")
        )

    @classmethod
    def _runtime_matches_locked_authority(
        cls,
        authority: Mapping[str, Any],
        *,
        subject: Mapping[str, Any],
        pointer: Mapping[str, Any],
        ownership: Mapping[str, Any],
        grade_code: str,
    ) -> bool:
        expected = {
            "runtime_session_id": str(subject.get("runtime_session_id") or ""),
            "principal_id": str(subject.get("principal_id") or ""),
            "family_id": str(subject.get("family_id") or ""),
            "child_id": str(subject.get("child_id") or ""),
            "learning_session_id": str(subject.get("learning_session_id") or ""),
            "runtime_classroom_id": str(subject.get("runtime_classroom_id") or ""),
            "upstream_classroom_id": str(subject.get("upstream_classroom_id") or ""),
            "session_task_id": str(subject.get("task_id") or ""),
            "session_course_id": str(subject.get("course_id") or ""),
            "session_course_version": str(subject.get("course_version") or ""),
            "session_package_id": str(subject.get("package_id") or ""),
            "candidate_grade_code": grade_code,
            "course_grade_code": grade_code,
            "candidate_release_id": str(pointer.get("release_id") or ""),
            "candidate_target_fingerprint": str(
                pointer.get("target_fingerprint") or ""
            ),
            "candidate_build_item_id": str(ownership.get("build_item_id") or ""),
        }
        return bool(
            all(
                str(authority.get(key) or "") == value
                for key, value in expected.items()
            )
            and cls._positive_integer(authority.get("session_package_version"))
            == cls._positive_integer(subject.get("package_version"))
        )

    @staticmethod
    def _positive_integer(value: object) -> int:
        if isinstance(value, bool):
            return 0
        try:
            parsed = int(value or 0)
        except (TypeError, ValueError):
            return 0
        return parsed if parsed > 0 else 0

    @staticmethod
    def _sha256_text(value: object) -> bool:
        return _SHA256.fullmatch(str(value or "")) is not None

    @staticmethod
    def _session_not_found() -> ApiError:
        return ApiError(
            "runtime_event_session_not_found",
            "课堂会话不存在或身份不匹配",
            404,
        )

    @staticmethod
    def _release_not_ready() -> ApiError:
        return ApiError(
            "student_learning_release_not_ready",
            "该年级正式课程尚未准备完成",
            409,
        )

    @classmethod
    def idempotency_key(
        cls,
        *,
        runtime_session_id: str,
        event: Mapping[str, Any],
    ) -> str:
        payload_json = cls._canonical_json(event["payload"])
        material = "\n".join(
            (
                runtime_session_id,
                RUNTIME_EVENT_SCHEMA,
                str(event["sequence"]),
                str(event["type"]),
                payload_json,
            )
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def _validate_scene_transition(
        self,
        conn: Any,
        *,
        stream: Mapping[str, Any],
        event: Mapping[str, Any],
        expected_scenes: tuple[dict[str, Any], ...],
    ) -> None:
        payload = event["payload"]
        scene_index = int(payload["sceneIndex"])
        scene_id = str(payload["sceneId"])
        expected_scene_count = len(expected_scenes)
        if scene_index >= expected_scene_count:
            raise ApiError(
                "runtime_event_scene_invalid",
                "课堂场景不在已发布课件范围内",
                409,
            )
        expected_scene = expected_scenes[scene_index]
        if scene_id != expected_scene["sceneId"]:
            raise ApiError(
                "runtime_event_scene_authority_mismatch",
                "课堂场景与已发布课件不一致",
                409,
            )
        if (
            event["type"] == "action_completed"
            and str(payload.get("actionId") or "")
            != expected_scene["completionActionId"]
        ):
            raise ApiError(
                "runtime_event_action_authority_mismatch",
                "课堂动作与已发布课件不一致",
                409,
            )
        if (
            event["type"] == "answer_submitted"
            and str(payload.get("questionId") or "")
            not in expected_scene["questionIds"]
        ):
            raise ApiError(
                "runtime_event_question_authority_mismatch",
                "课堂题目与已发布课件不一致",
                409,
            )
        if (
            event["type"] == "classroom_completed"
            and scene_index != expected_scene_count - 1
        ):
            raise ApiError(
                "runtime_event_completion_scene_invalid",
                "课堂只能由最后一个已发布场景完成",
                409,
            )
        existing = self.repository.get_scene_identity(
            conn,
            runtime_session_id=str(stream["runtime_session_id"]),
            scene_index=scene_index,
        )
        if existing is not None and str(existing.get("scene_id") or "") != scene_id:
            raise ApiError(
                "runtime_event_scene_conflict",
                "课堂场景编号与已记录版本不一致",
                409,
            )
        if event["type"] == "scene_entered":
            if existing is None:
                evidence = self.repository.scene_evidence(
                    conn,
                    runtime_session_id=str(stream["runtime_session_id"]),
                )
                if scene_index != int(evidence.get("scene_count") or 0):
                    raise ApiError(
                        "runtime_event_scene_gap",
                        "课堂场景进度不连续",
                        409,
                    )
            return
        if existing is None:
            raise ApiError(
                "runtime_event_scene_not_entered",
                "请先进入当前课堂场景",
                409,
            )

    def _require_completion_evidence(
        self,
        conn: Any,
        *,
        authority: Mapping[str, Any],
        expected_scene_count: int,
    ) -> None:
        evidence = self._authoritative_scene_evidence(
            conn,
            authority=authority,
        )
        objectives = self._interaction_objectives(authority)
        completed_operations = self._completed_interactions(objectives, self._interaction_evidence(conn, authority=authority)) if objectives else set()
        if (
            len(completed_operations) != len(objectives)
            or int(evidence.get("scene_count") or 0) != expected_scene_count
            or int(evidence.get("action_scene_count") or 0) != expected_scene_count
            or int(evidence.get("maximum_scene_index") or -1)
            != expected_scene_count - 1
            or not self.learning_service.authoritative_runtime_questions_complete(
                conn,
                authority=authority,
            )
        ):
            raise ApiError(
                "runtime_event_evidence_incomplete",
                "课堂场景、互动或作答证据尚未完成",
                409,
            )

    def _authoritative_scene_evidence(
        self,
        conn: Any,
        *,
        authority: Mapping[str, Any],
    ) -> Mapping[str, int]:
        return self.repository.learning_session_scene_evidence(
            conn,
            family_id=str(authority["family_id"]),
            child_id=str(authority["child_id"]),
            learning_session_id=str(authority["learning_session_id"]),
            runtime_classroom_id=str(authority["runtime_classroom_id"]),
            release_id=str(authority["candidate_release_id"]),
            target_fingerprint=str(authority["candidate_target_fingerprint"]),
        )

    @staticmethod
    def _interaction_objectives(authority: Mapping[str, Any]) -> list[dict[str, Any]]:
        manifest = authority.get("feature_manifest_json")
        if isinstance(manifest, str):
            try:
                manifest = json.loads(manifest)
            except (ValueError, TypeError):
                manifest = None
        if not isinstance(manifest, Mapping):
            raise ApiError("runtime_event_authority_invalid", "课程互动合同不可用", 409)
        generation = manifest.get("generationContract") or {}
        professional = manifest.get("professionalCreation") or {}
        formal = manifest.get("formalEvidence") or {}
        policy = generation.get("professionalCreationPolicy") if isinstance(generation, Mapping) else None
        selected = policy.get("interactionDesignPolicy") if isinstance(policy, Mapping) else None
        claimed = (isinstance(professional, Mapping) and "interactionDesign" in professional) or (isinstance(formal, Mapping) and "interactionDesign" in formal)
        if selected is None and not claimed:
            return []  # Historical frozen courses keep their original completion contract.
        try:
            validate_interaction_manifest(manifest)
            receipt = professional["interactionDesign"]
            if receipt["stageId"] != authority["upstream_classroom_id"]:
                raise ValueError("interaction classroom mismatch")
            return receipt["objectives"]
        except (ValueError, TypeError, KeyError) as exc:
            raise ApiError("runtime_event_authority_invalid", "课程互动合同与已发布版本不一致", 409) from exc

    @staticmethod
    def _operation_matches(objective: Mapping[str, Any], payload: Mapping[str, Any]) -> bool:
        operation, feedback = objective["operation"], objective["feedback"]
        text = payload.get("feedbackText")
        return bool(payload.get("objectiveIndex") == objective["objectiveIndex"]
            and payload.get("sceneId") == operation["sceneId"]
            and payload.get("controlSelector") == operation["controlSelector"]
            and payload.get("action") == operation["action"]
            and payload.get("value") == ("" if operation["action"] == "click" else operation.get("value"))
            and isinstance(text, str) and feedback["textIncludes"] in text and feedback["reasonQuote"] in text)

    @classmethod
    def _completed_interactions(cls, objectives: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> set[int]:
        return {item["objectiveIndex"] for item in objectives if any(
            row.get("event_type") == "interaction_completed" and cls._operation_matches(item, row.get("payload") or {})
            for row in evidence)}

    def _interaction_evidence(self, conn: Any, *, authority: Mapping[str, Any]) -> list[dict[str, Any]]:
        return self.repository.learning_session_interaction_evidence(conn,
            family_id=str(authority["family_id"]), child_id=str(authority["child_id"]),
            learning_session_id=str(authority["learning_session_id"]),
            runtime_classroom_id=str(authority["runtime_classroom_id"]),
            release_id=str(authority["candidate_release_id"]),
            target_fingerprint=str(authority["candidate_target_fingerprint"]))

    @classmethod
    def _event(cls, value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping) or set(value) != {
            "schemaVersion",
            "sequence",
            "type",
            "payload",
            "idempotencyKey",
        }:
            raise ApiError("invalid_runtime_event", "课堂事件字段不完整")
        if value.get("schemaVersion") != RUNTIME_EVENT_SCHEMA:
            raise ApiError("invalid_runtime_event", "课堂事件版本不受支持")
        sequence = value.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or not 1 <= sequence <= 1_000_000:
            raise ApiError("invalid_runtime_event_sequence", "课堂事件序号无效")
        event_type = str(value.get("type") or "")
        if event_type not in _EVENT_TYPES:
            raise ApiError("invalid_runtime_event_type", "课堂事件类型不受支持")
        payload = value.get("payload")
        if not isinstance(payload, Mapping) or set(payload) != _PAYLOAD_FIELDS[event_type]:
            raise ApiError(
                "invalid_runtime_event_payload",
                "课堂事件内容包含不受支持的字段",
            )
        clean_payload = dict(payload)
        scene_index = clean_payload.get("sceneIndex")
        if (
            isinstance(scene_index, bool)
            or not isinstance(scene_index, int)
            or not 0 <= scene_index < 60
        ):
            raise ApiError("invalid_runtime_event_payload", "课堂场景序号无效")
        clean_payload["sceneId"] = cls._identifier(
            clean_payload.get("sceneId"), "sceneId", maximum=128
        )
        if event_type == "action_completed":
            clean_payload["actionId"] = cls._identifier(
                clean_payload.get("actionId"), "actionId", maximum=128
            )
        if event_type == "answer_submitted":
            clean_payload["questionId"] = cls._identifier(
                clean_payload.get("questionId"), "questionId", maximum=128
            )
            attempt = clean_payload.get("attemptNumber")
            if isinstance(attempt, bool) or attempt != 1:
                raise ApiError("invalid_runtime_event_payload", "作答次数无效")
            response = clean_payload.get("response")
            if isinstance(response, Mapping) or response is None:
                raise ApiError("invalid_runtime_event_payload", "作答内容格式无效")
            try:
                encoded_response = cls._canonical_json(response)
            except (TypeError, ValueError) as exc:
                raise ApiError("invalid_runtime_event_payload", "作答内容格式无效") from exc
            if len(encoded_response.encode("utf-8")) > 4096:
                raise ApiError("invalid_runtime_event_payload", "作答内容过大")
        if event_type == "interaction_completed":
            index, selector = clean_payload.get("objectiveIndex"), clean_payload.get("controlSelector")
            action, operation_value, feedback = clean_payload.get("action"), clean_payload.get("value"), clean_payload.get("feedbackText")
            if (type(index) is not int or not 0 <= index < 30 or not isinstance(selector, str)
                    or not re.fullmatch(r"#[A-Za-z][A-Za-z0-9_-]{0,98}", selector)
                    or action not in ("click", "fill", "range", "select")
                    or not isinstance(operation_value, str) or len(operation_value) > 500 or (action == "click" and operation_value != "")
                    or not isinstance(feedback, str) or not feedback.strip() or len(feedback) > 2000):
                raise ApiError("invalid_runtime_event_payload", "课程操作证据无效")
        if event_type == "asr_transcribed":
            turn_id = clean_payload.get("turnId")
            if (
                not isinstance(turn_id, str)
                or len(turn_id) > 128
                or not _IDENTIFIER.fullmatch(turn_id)
            ):
                raise ApiError("invalid_runtime_event_payload", "语音轮次标识无效")
            clean_payload["turnId"] = turn_id
            transcript = clean_payload.get("transcript")
            if (
                not isinstance(transcript, str)
                or not transcript
                or transcript.strip() != transcript
                or len(transcript.encode("utf-8")) > 4096
            ):
                raise ApiError("invalid_runtime_event_payload", "语音转写内容无效")
        idempotency_key = str(value.get("idempotencyKey") or "")
        if not _SHA256.fullmatch(idempotency_key):
            raise ApiError(
                "runtime_event_idempotency_invalid",
                "课堂事件幂等标识无效",
            )
        return {
            "schemaVersion": RUNTIME_EVENT_SCHEMA,
            "sequence": sequence,
            "type": event_type,
            "payload": clean_payload,
            "idempotencyKey": idempotency_key,
        }

    @staticmethod
    def _validate_authority(
        authority: Mapping[str, Any],
        *,
        runtime_session_id: str,
        learning_session_id: str,
        upstream_classroom_id: str,
        now: int,
    ) -> tuple[dict[str, Any], ...]:
        if (
            str(authority.get("runtime_session_id") or "") != runtime_session_id
            or str(authority.get("learning_session_id") or "") != learning_session_id
            or str(authority.get("upstream_classroom_id") or "")
            != upstream_classroom_id
            or authority.get("runtime_revoked_at") is not None
        ):
            raise ApiError(
                "runtime_event_session_not_found",
                "课堂会话不存在或身份不匹配",
                404,
            )
        if int(authority.get("runtime_expires_at") or 0) < now:
            raise ApiError("runtime_event_session_expired", "课堂登录已过期", 401)
        manifest = authority.get("feature_manifest_json")
        if isinstance(manifest, str):
            try:
                manifest = json.loads(manifest)
            except (json.JSONDecodeError, TypeError, ValueError):
                manifest = None
        formal_evidence = (
            manifest.get("formalEvidence")
            if isinstance(manifest, Mapping)
            else None
        )
        event_authority = (
            formal_evidence.get("runtimeEventAuthority")
            if isinstance(formal_evidence, Mapping)
            else None
        )
        authority_scenes = (
            event_authority.get("scenes")
            if isinstance(event_authority, Mapping)
            and event_authority.get("schemaVersion")
            == "mira.openmaic.runtime-event-authority.v1"
            else None
        )
        if (
            authority.get("runtime_status") != "ready"
            or not authority.get("candidate_build_item_id")
            or not authority.get("candidate_release_id")
            or not _SHA256.fullmatch(
                str(authority.get("candidate_target_fingerprint") or "")
            )
            or authority.get("session_package_id")
            != authority.get("runtime_package_id")
            or int(authority.get("session_package_version") or 0)
            != int(authority.get("runtime_package_version") or 0)
            or not isinstance(manifest, Mapping)
            or manifest.get("schemaVersion") != "mira.openmaic.runtime-features.v2"
            or not isinstance(manifest.get("platform"), Mapping)
            or manifest["platform"].get("assessmentAuthority") != "mira_backend"
            or isinstance(manifest.get("sceneCount"), bool)
            or not isinstance(manifest.get("sceneCount"), int)
            or not 1 <= int(manifest["sceneCount"]) <= 60
            or not isinstance(authority_scenes, list)
            or len(authority_scenes) != int(manifest["sceneCount"])
        ):
            raise ApiError(
                "runtime_event_authority_invalid",
                "正式课堂的事件权威合同无效",
                409,
            )
        normalized_scenes: list[dict[str, Any]] = []
        question_ids: list[str] = []
        for expected_index, scene in enumerate(authority_scenes):
            if (
                not isinstance(scene, Mapping)
                or set(scene)
                != {
                    "sceneIndex",
                    "sceneId",
                    "completionActionId",
                    "questionIds",
                }
                or isinstance(scene.get("sceneIndex"), bool)
                or scene.get("sceneIndex") != expected_index
                or not isinstance(scene.get("questionIds"), list)
                or not _IDENTIFIER.fullmatch(str(scene.get("sceneId") or ""))
                or len(str(scene.get("sceneId") or "")) > 128
                or not _IDENTIFIER.fullmatch(
                    str(scene.get("completionActionId") or "")
                )
                or len(str(scene.get("completionActionId") or "")) > 128
                or any(
                    not _IDENTIFIER.fullmatch(str(question_id or ""))
                    or len(str(question_id or "")) > 128
                    for question_id in scene["questionIds"]
                )
            ):
                raise ApiError(
                    "runtime_event_authority_invalid",
                    "正式课堂的事件权威合同无效",
                    409,
                )
            normalized_question_ids = [
                str(question_id) for question_id in scene["questionIds"]
            ]
            question_ids.extend(normalized_question_ids)
            normalized_scenes.append(
                {
                    "sceneIndex": expected_index,
                    "sceneId": str(scene["sceneId"]),
                    "completionActionId": str(scene["completionActionId"]),
                    "questionIds": normalized_question_ids,
                }
            )
        if len(question_ids) != 4 or len(set(question_ids)) != 4:
            raise ApiError(
                "runtime_event_authority_invalid",
                "正式课堂的事件权威合同无效",
                409,
            )
        return tuple(normalized_scenes)

    @staticmethod
    def _validate_stream(
        stream: Mapping[str, Any],
        *,
        authority: Mapping[str, Any],
        expected_scene_count: int,
    ) -> None:
        expected = {
            "runtime_session_id": authority["runtime_session_id"],
            "learning_session_id": authority["learning_session_id"],
            "runtime_classroom_id": authority["runtime_classroom_id"],
            "upstream_classroom_id": authority["upstream_classroom_id"],
            "family_id": authority["family_id"],
            "child_id": authority["child_id"],
            "release_id": authority["candidate_release_id"],
            "target_fingerprint": authority["candidate_target_fingerprint"],
        }
        if any(str(stream.get(key) or "") != str(value) for key, value in expected.items()) or int(
            stream.get("expected_scene_count") or 0
        ) != expected_scene_count:
            raise ApiError(
                "runtime_event_stream_conflict",
                "课堂事件流与已冻结课程版本不一致",
                409,
            )

    @staticmethod
    def _identifier(value: object, field: str, *, maximum: int) -> str:
        text = str(value or "").strip()
        if len(text) > maximum or not _IDENTIFIER.fullmatch(text):
            raise ApiError("invalid_runtime_event_identity", f"{field} 格式无效")
        return text

    @staticmethod
    def _canonical_json(value: object) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    @classmethod
    def _sha256(cls, value: object) -> str:
        return hashlib.sha256(cls._canonical_json(value).encode("utf-8")).hexdigest()
