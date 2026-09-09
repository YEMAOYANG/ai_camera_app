from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import unittest

from core.errors import ApiError
from services.openmaic_runtime_event_service import OpenMaicRuntimeEventService


NOW = 1_777_777_777_000
SCHEMA = "mira.openmaic.student-runtime-event.v1"


def _idempotency_key(*, sequence: int, event_type: str, payload: dict) -> str:
    canonical_payload = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    material = "\n".join(
        ("runtime-session-1", SCHEMA, str(sequence), event_type, canonical_payload)
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _event(sequence: int, event_type: str, payload: dict) -> dict:
    return {
        "schemaVersion": SCHEMA,
        "sequence": sequence,
        "type": event_type,
        "payload": payload,
        "idempotencyKey": _idempotency_key(
            sequence=sequence,
            event_type=event_type,
            payload=payload,
        ),
    }


class _Repository:
    def __init__(self):
        self.authority = {
            "runtime_session_id": "runtime-session-1",
            "learning_session_id": "learning-session-1",
            "runtime_classroom_id": "runtime-row-1",
            "upstream_classroom_id": "classroom-1",
            "family_id": "family-1",
            "child_id": "child-1",
            "principal_id": "principal-1",
            "runtime_expires_at": NOW + 60_000,
            "runtime_revoked_at": None,
            "runtime_status": "ready",
            "candidate_release_id": "release-1",
            "candidate_build_item_id": "build-item-1",
            "candidate_grade_code": "primary_1",
            "candidate_target_fingerprint": "a" * 64,
            "feature_manifest_json": {
                "schemaVersion": "mira.openmaic.runtime-features.v2",
                "sceneCount": 10,
                "platform": {"assessmentAuthority": "mira_backend"},
                "formalEvidence": {
                    "runtimeEventAuthority": {
                        "schemaVersion": "mira.openmaic.runtime-event-authority.v1",
                        "scenes": [
                            {
                                "sceneIndex": index,
                                "sceneId": f"scene-{index}",
                                "completionActionId": f"action-{index}",
                                "questionIds": (
                                    ["q1"]
                                    if index == 0
                                    else ["q2", "q3"]
                                    if index == 5
                                    else ["q4"]
                                    if index == 6
                                    else []
                                ),
                            }
                            for index in range(10)
                        ],
                    }
                },
            },
            "session_status": "in_progress",
            "session_current_question_index": 0,
            "session_correct_count": 0,
            "session_attempted_count": 0,
            "session_answers_json": "[]",
            "session_task_id": "task-1",
            "session_course_id": "course-1",
            "session_course_version": "1",
            "session_package_id": "package-1",
            "session_package_version": 1,
            "runtime_package_id": "package-1",
            "runtime_package_version": 1,
            "course_content_json": "{}",
            "course_grade_code": "primary_1",
            "course_subject": "math",
            "course_node_code": "number_sense_20",
        }
        self.child = {
            "id": "child-1",
            "family_id": "family-1",
            "education_stage_code": "primary",
            "grade_code": "primary_1",
            "grade_selection_revision": 1,
        }
        self.principal = {
            "id": "principal-1",
            "family_id": "family-1",
            "child_id": "child-1",
            "status": "active",
        }
        self.task = {
            "id": "task-1",
            "family_id": "family-1",
            "child_id": "child-1",
            "type": "learning",
            "learning_course_id": "course-1",
            "learning_course_version": "1",
        }
        self.session = {
            "id": "learning-session-1",
            "family_id": "family-1",
            "child_id": "child-1",
            "task_id": "task-1",
            "course_id": "course-1",
            "course_version": "1",
            "lesson_package_id": "package-1",
            "lesson_package_version": 1,
            "lesson_package_content_hash": "b" * 64,
        }
        self.pointer = {
            "grade_code": "primary_1",
            "pointer_revision": 1,
            "target_fingerprint": "a" * 64,
            "contract_version": "mira.learning.formal-publication.v1",
            "release_id": "release-1",
            "history_id": "history-1",
            "activated_at": NOW - 1_000,
        }
        self.plan = {
            "id": "plan-1",
            "family_id": "family-1",
            "child_id": "child-1",
            "grade_code": "primary_1",
            "grade_selection_revision": 1,
            "status": "ready",
            "stage": "completed",
            "progress_percent": 100,
            "total_course_count": 30,
            "ready_course_count": 30,
            "failed_course_count": 0,
            "content_target_count": 30,
            "content_candidate_count": 30,
            "content_failed_count": 0,
            "classroom_ready_count": 30,
            "speech_ready_count": 30,
            "validation_ready_count": 30,
            "published_course_count": 30,
            "formal_ready_at": NOW - 500,
            "completed_at": NOW - 500,
            "superseded_at": None,
            "catalog_release_id": "release-1",
            "target_fingerprint": "a" * 64,
            "formal_contract_version": "mira.learning.formal-publication.v1",
            "formal_publication_history_id": "history-1",
            "formal_publication_receipt_hash": "c" * 64,
        }
        self.history = {
            "id": "history-1",
            "grade_code": "primary_1",
            "pointer_revision": 1,
            "target_fingerprint": "a" * 64,
            "contract_version": "mira.learning.formal-publication.v1",
            "release_id": "release-1",
            "activation_source": "formal_publication",
            "publication_receipt_hash": "c" * 64,
            "superseded_at": None,
        }
        self.course_ownership = {
            "release_id": "release-1",
            "release_status": "published",
            "release_quality_status": "ready",
            "release_ready_item_count": 30,
            "release_activated_at": NOW - 1_000,
            "release_retired_at": None,
            "release_item_status": "published",
            "release_item_quality_status": "ready",
            "release_item_retired_at": None,
            "grade_code": "primary_1",
            "course_id": "course-1",
            "course_version": "1",
            "package_id": "package-1",
            "package_version": 1,
            "build_item_id": "build-item-1",
            "binding_history_id": "history-1",
            "binding_pointer_revision": 1,
            "binding_target_fingerprint": "a" * 64,
            "binding_contract_version": "mira.learning.formal-publication.v1",
            "runtime_classroom_id": "runtime-row-1",
            "upstream_classroom_id": "classroom-1",
        }
        self.stream = None
        self.events: list[dict] = []
        self.scene_ids: dict[int, str] = {}
        self.action_scene_indices: set[int] = set()
        self.prior_scene_indices: set[int] = set()
        self.prior_action_scene_indices: set[int] = set()
        self.lock_calls: list[str] = []

    @contextmanager
    def transaction(self):
        yield object()

    def get_runtime_subject(self, _conn, **kwargs):
        self.lock_calls.append("runtime_subject_snapshot")
        if kwargs != {
            "runtime_session_id": self.authority["runtime_session_id"],
            "learning_session_id": self.authority["learning_session_id"],
            "upstream_classroom_id": self.authority["upstream_classroom_id"],
        }:
            return None
        return {
            "runtime_session_id": self.authority["runtime_session_id"],
            "principal_id": self.authority["principal_id"],
            "family_id": self.authority["family_id"],
            "child_id": self.authority["child_id"],
            "learning_session_id": self.authority["learning_session_id"],
            "runtime_classroom_id": self.authority["runtime_classroom_id"],
            "upstream_classroom_id": self.authority["upstream_classroom_id"],
            "task_id": self.authority["session_task_id"],
            "course_id": self.authority["session_course_id"],
            "course_version": self.authority["session_course_version"],
            "package_id": self.authority["session_package_id"],
            "package_version": self.authority["session_package_version"],
        }

    def get_child_for_update(self, _conn, **_kwargs):
        self.lock_calls.append("child")
        return None if self.child is None else dict(self.child)

    def get_principal_for_update(self, _conn, **_kwargs):
        self.lock_calls.append("principal")
        return None if self.principal is None else dict(self.principal)

    def get_task_for_update(self, _conn, **_kwargs):
        self.lock_calls.append("task")
        return None if self.task is None else dict(self.task)

    def get_learning_session_for_update(self, _conn, **_kwargs):
        self.lock_calls.append("learning_session")
        return None if self.session is None else dict(self.session)

    def get_formal_pointer_for_update(self, _conn, **_kwargs):
        self.lock_calls.append("formal_pointer")
        return None if self.pointer is None else dict(self.pointer)

    def get_formal_plan_for_update(self, _conn, **_kwargs):
        self.lock_calls.append("formal_plan")
        return None if self.plan is None else dict(self.plan)

    def get_formal_history_for_update(self, _conn, **_kwargs):
        self.lock_calls.append("formal_history")
        return None if self.history is None else dict(self.history)

    def get_formal_course_ownership_for_update(self, _conn, **_kwargs):
        self.lock_calls.append("formal_course_ownership")
        return (
            None
            if self.course_ownership is None
            else dict(self.course_ownership)
        )

    def get_runtime_authority(self, _conn, **kwargs):
        self.lock_calls.append("runtime_authority")
        if kwargs != {
            "runtime_session_id": self.authority["runtime_session_id"],
            "learning_session_id": self.authority["learning_session_id"],
            "upstream_classroom_id": self.authority["upstream_classroom_id"],
            "for_update": True,
        }:
            return None
        return dict(self.authority)

    def create_or_get_stream(self, _conn, *, authority, now):
        self.lock_calls.append("runtime_stream")
        if self.stream is None:
            self.stream = {
                "runtime_session_id": authority["runtime_session_id"],
                "learning_session_id": authority["learning_session_id"],
                "runtime_classroom_id": authority["runtime_classroom_id"],
                "upstream_classroom_id": authority["upstream_classroom_id"],
                "family_id": authority["family_id"],
                "child_id": authority["child_id"],
                "release_id": authority["candidate_release_id"],
                "target_fingerprint": authority["candidate_target_fingerprint"],
                "expected_scene_count": 10,
                "last_sequence": 0,
                "completed_at": None,
                "report_id": None,
            }
        return dict(self.stream)

    def get_stream(self, _conn, *, runtime_session_id, for_update=False):
        return None if self.stream is None else dict(self.stream)

    def get_event_by_idempotency(self, _conn, *, runtime_session_id, idempotency_key):
        return next(
            (
                dict(item)
                for item in self.events
                if item["idempotency_key"] == idempotency_key
            ),
            None,
        )

    def get_event_by_sequence(self, _conn, *, runtime_session_id, sequence):
        return next(
            (dict(item) for item in self.events if item["sequence"] == sequence),
            None,
        )

    def get_scene_identity(self, _conn, *, runtime_session_id, scene_index):
        scene_id = self.scene_ids.get(scene_index)
        return None if scene_id is None else {"scene_id": scene_id}

    def scene_evidence(self, _conn, *, runtime_session_id):
        return {
            "scene_count": len(self.scene_ids),
            "action_scene_count": len(self.action_scene_indices),
            "maximum_scene_index": max(self.scene_ids, default=-1),
        }

    def learning_session_scene_evidence(self, _conn, **kwargs):
        assert kwargs == {
            "family_id": self.authority["family_id"],
            "child_id": self.authority["child_id"],
            "learning_session_id": self.authority["learning_session_id"],
            "runtime_classroom_id": self.authority["runtime_classroom_id"],
            "release_id": self.authority["candidate_release_id"],
            "target_fingerprint": self.authority["candidate_target_fingerprint"],
        }
        scene_indices = self.prior_scene_indices | set(self.scene_ids)
        action_indices = self.prior_action_scene_indices | self.action_scene_indices
        return {
            "scene_count": len(scene_indices),
            "action_scene_count": len(action_indices),
            "maximum_scene_index": max(scene_indices, default=-1),
        }

    def answered_question_ids(self, _conn, *, runtime_session_id):
        return [
            str(item["question_id"])
            for item in self.events
            if item.get("event_type") == "answer_submitted"
            and item.get("question_id")
        ]

    def append_event(
        self,
        _conn,
        *,
        stream,
        event,
        request_sha256,
        authoritative,
        response,
        now,
    ):
        row = {
            "runtime_session_id": stream["runtime_session_id"],
            "sequence": event["sequence"],
            "idempotency_key": event["idempotencyKey"],
            "request_sha256": request_sha256,
            "event_type": event["type"],
            "scene_index": event["payload"].get("sceneIndex"),
            "scene_id": event["payload"].get("sceneId"),
            "question_id": event["payload"].get("questionId"),
            "payload": dict(event["payload"]),
            "response_json": json.dumps(response, sort_keys=True, separators=(",", ":")),
        }
        self.events.append(row)
        if event["type"] == "scene_entered":
            self.scene_ids[event["payload"]["sceneIndex"]] = event["payload"]["sceneId"]
        if event["type"] == "action_completed":
            self.action_scene_indices.add(event["payload"]["sceneIndex"])
        self.stream["last_sequence"] = event["sequence"]
        if response.get("completed"):
            self.stream["completed_at"] = now
            self.stream["report_id"] = response["reportId"]
        return row

    @staticmethod
    def decode_response(row):
        return json.loads(row["response_json"])


class _LearningService:
    def __init__(self):
        self.answer_calls = 0
        self.complete_calls = 0
        self.questions_complete = False
        self.answered_question_ids: list[str] = []

    def record_authoritative_runtime_answer(
        self,
        _conn,
        *,
        authority,
        question_id,
        submitted_answer,
        attempt_number,
        now,
    ):
        self.answer_calls += 1
        self.questions_complete = True
        if question_id not in self.answered_question_ids:
            self.answered_question_ids.append(question_id)
        return {
            "questionId": question_id,
            "attemptNumber": attempt_number,
            "correct": submitted_answer == "12",
            "evaluatorVersion": "mira.learning.question-evaluator.v1",
            "questionsComplete": True,
        }

    def authoritative_runtime_questions_complete(self, _conn, *, authority):
        return self.questions_complete

    def authoritative_runtime_answered_question_ids(self, _conn, *, authority):
        return list(self.answered_question_ids)

    def complete_authoritative_runtime_session(self, _conn, *, authority, now):
        self.complete_calls += 1
        return {"id": "report-1"}


class _TaskRuntimeCoordinator:
    def __init__(self):
        self.started: list[tuple[str, str]] = []
        self.completed: list[tuple[str, str]] = []

    def learning_classroom_started(self, *, family_id: str, task_id: str):
        self.started.append((family_id, task_id))

    def learning_classroom_completed(self, *, family_id: str, task_id: str):
        self.completed.append((family_id, task_id))


class OpenMaicRuntimeEventBridgeTest(unittest.TestCase):
    def setUp(self):
        self.repository = _Repository()
        self.learning = _LearningService()
        self.task_runtime = _TaskRuntimeCoordinator()
        self.service = OpenMaicRuntimeEventService(
            repository=self.repository,
            learning_service=self.learning,
            task_runtime_service=self.task_runtime,
            clock=lambda: NOW,
        )

    def _record(self, data: dict):
        return self.service.record(
            runtime_session_id="runtime-session-1",
            learning_session_id="learning-session-1",
            upstream_classroom_id="classroom-1",
            data=data,
        )

    def test_progressive_binding_accepts_runtime_events_without_grade_pointer(self):
        original_subject = self.repository.get_runtime_subject

        def progressive_subject(conn, **kwargs):
            subject = original_subject(conn, **kwargs)
            subject.update(
                {
                    "package_content_hash": "b" * 64,
                    "binding_authority_kind": "progressive_plan",
                    "binding_history_id": None,
                    "binding_pointer_revision": None,
                    "binding_plan_id": "plan-1",
                    "binding_grade_revision": 1,
                    "binding_release_id": "release-1",
                    "binding_grade_code": "primary_1",
                    "binding_target_fingerprint": "a" * 64,
                    "binding_contract_version": (
                        "mira.learning.formal-publication.v1"
                    ),
                    "binding_runtime_contract_version": (
                        "mira.learning.candidate-runtime-binding.v1"
                    ),
                    "binding_build_item_id": "build-item-1",
                    "binding_course_id": "course-1",
                    "binding_course_version": "1",
                    "binding_package_id": "package-1",
                    "binding_package_version": 1,
                    "binding_package_content_hash": "b" * 64,
                }
            )
            return subject

        self.repository.get_runtime_subject = progressive_subject
        self.repository.course_ownership.update(
            {
                "binding_authority_kind": "progressive_plan",
                "binding_history_id": None,
                "binding_pointer_revision": None,
                "binding_plan_id": "plan-1",
                "binding_grade_revision": 1,
                "binding_target_fingerprint": "a" * 64,
                "binding_contract_version": (
                    "mira.learning.formal-publication.v1"
                ),
                "binding_runtime_contract_version": (
                    "mira.learning.candidate-runtime-binding.v1"
                ),
                "binding_package_content_hash": "b" * 64,
                "build_item_status": "ready",
                "build_job_id": "build-1",
                "authority_plan_id": "plan-1",
                "authority_plan_family_id": "family-1",
                "authority_plan_child_id": "child-1",
                "authority_plan_grade_code": "primary_1",
                "authority_plan_grade_revision": 1,
                "authority_plan_build_id": "build-1",
                "authority_plan_release_id": "release-1",
                "authority_plan_fingerprint": "a" * 64,
                "authority_plan_status": "running",
            }
        )

        receipt = self._record(
            _event(1, "scene_entered", {"sceneIndex": 0, "sceneId": "scene-0"})
        )

        self.assertEqual(receipt["sequence"], 1)
        self.assertNotIn("formal_pointer", self.repository.lock_calls)
        self.assertIn("formal_course_ownership", self.repository.lock_calls)

    def test_status_resumes_the_server_sequence_without_accepting_browser_identity(self):
        initial = self.service.status(
            runtime_session_id="runtime-session-1",
            learning_session_id="learning-session-1",
            upstream_classroom_id="classroom-1",
        )
        self.assertEqual(initial["nextSequence"], 1)
        self.assertFalse(initial["completed"])
        self.assertFalse(initial["completionReady"])

        self._record(
            _event(1, "scene_entered", {"sceneIndex": 0, "sceneId": "scene-0"})
        )
        resumed = self.service.status(
            runtime_session_id="runtime-session-1",
            learning_session_id="learning-session-1",
            upstream_classroom_id="classroom-1",
        )
        self.assertEqual(resumed["nextSequence"], 2)
        self.assertEqual(resumed["lastSequence"], 1)
        self.assertEqual(resumed["releaseId"], "release-1")
        self.assertEqual(resumed["sceneEnteredCount"], 1)
        self.assertEqual(resumed["actionCompletedSceneCount"], 0)
        self.assertFalse(resumed["questionsComplete"])
        self.assertFalse(resumed["completionReady"])
        self.assertEqual(
            self.task_runtime.started,
            [("family-1", "task-1")],
        )

    def test_status_restores_authoritative_answers_from_an_earlier_runtime_session(self):
        self.learning.answered_question_ids = ["q1", "q2"]

        status = self.service.status(
            runtime_session_id="runtime-session-1",
            learning_session_id="learning-session-1",
            upstream_classroom_id="classroom-1",
        )

        self.assertEqual(status["answeredQuestionIds"], ["q1", "q2"])
        self.assertEqual(status["nextSequence"], 1)
        self.assertFalse(status["completionReady"])

    def test_session_and_classroom_identifiers_accept_the_full_255_column_boundary(self):
        learning_session_id = "l" + "a" * 254
        upstream_classroom_id = "c" + "b" * 254
        self.repository.authority.update(
            learning_session_id=learning_session_id,
            upstream_classroom_id=upstream_classroom_id,
        )

        status = self.service.status(
            runtime_session_id="runtime-session-1",
            learning_session_id=learning_session_id,
            upstream_classroom_id=upstream_classroom_id,
        )

        self.assertEqual(status["learningSessionId"], learning_session_id)
        self.assertEqual(status["classroomId"], upstream_classroom_id)
        with self.assertRaises(ApiError):
            self.service.status(
                runtime_session_id="runtime-session-1",
                learning_session_id=learning_session_id + "x",
                upstream_classroom_id=upstream_classroom_id,
            )
        with self.assertRaises(ApiError):
            self.service.status(
                runtime_session_id="r" + "x" * 128,
                learning_session_id=learning_session_id,
                upstream_classroom_id=upstream_classroom_id,
            )

    def test_answer_rejects_client_score_and_returns_server_evaluation(self):
        forged = _event(
            1,
            "answer_submitted",
            {
                "sceneIndex": 0,
                "sceneId": "scene-0",
                "questionId": "q1",
                "response": "12",
                "attemptNumber": 1,
                "score": 100,
            },
        )
        with self.assertRaises(ApiError) as raised:
            self._record(forged)
        self.assertEqual(raised.exception.code, "invalid_runtime_event_payload")
        self.assertEqual(self.learning.answer_calls, 0)

        self._record(_event(1, "scene_entered", {"sceneIndex": 0, "sceneId": "scene-0"}))
        result = self._record(
            _event(
                2,
                "answer_submitted",
                {
                    "sceneIndex": 0,
                    "sceneId": "scene-0",
                    "questionId": "q1",
                    "response": "12",
                    "attemptNumber": 1,
                },
            )
        )
        self.assertTrue(result["authoritativeEvaluation"]["correct"])
        self.assertEqual(result["authoritativeEvaluation"]["questionId"], "q1")
        self.assertNotIn("score", result)
        resumed = self.service.status(
            runtime_session_id="runtime-session-1",
            learning_session_id="learning-session-1",
            upstream_classroom_id="classroom-1",
        )
        self.assertEqual(resumed["answeredQuestionIds"], ["q1"])

    def test_asr_transcript_appends_non_assessment_evidence_only_after_scene_entry(self):
        transcript = {
            "sceneIndex": 0,
            "sceneId": "scene-0",
            "turnId": "asr-turn-1",
            "transcript": "我觉得答案是十二。",
        }
        with self.assertRaises(ApiError) as before_scene:
            self._record(_event(1, "asr_transcribed", transcript))
        self.assertEqual(before_scene.exception.code, "runtime_event_scene_not_entered")

        self._record(
            _event(1, "scene_entered", {"sceneIndex": 0, "sceneId": "scene-0"})
        )
        try:
            receipt = self._record(_event(2, "asr_transcribed", transcript))
        except ApiError as exc:
            self.fail(f"ASR transcript was rejected: {exc.code}")

        self.assertEqual(receipt["type"], "asr_transcribed")
        self.assertIsNone(receipt["authoritativeEvaluation"])
        self.assertEqual(self.learning.answer_calls, 0)
        self.assertEqual(self.learning.complete_calls, 0)
        self.assertEqual(self.repository.events[-1]["event_type"], "asr_transcribed")
        self.assertEqual(self.repository.events[-1]["payload"], transcript)
        status = self.service.status(
            runtime_session_id="runtime-session-1",
            learning_session_id="learning-session-1",
            upstream_classroom_id="classroom-1",
        )
        self.assertFalse(status["questionsComplete"])
        self.assertFalse(status["completionReady"])

    def test_asr_transcript_contract_rejects_empty_oversized_and_forged_fields(self):
        base = {
            "sceneIndex": 0,
            "sceneId": "scene-0",
            "turnId": "asr-turn-1",
            "transcript": "十二",
        }
        invalid_payloads = [
            {**base, "transcript": ""},
            {**base, "transcript": "x" * 4097},
            {**base, "turnId": "bad turn id"},
            {**base, "providerId": "browser-forged-provider"},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ApiError) as raised:
                    self._record(_event(1, "asr_transcribed", payload))
                self.assertEqual(raised.exception.code, "invalid_runtime_event_payload")

    def test_exact_replay_returns_identical_receipt_without_rescoring(self):
        self._record(_event(1, "scene_entered", {"sceneIndex": 0, "sceneId": "scene-0"}))
        submitted = _event(
            2,
            "answer_submitted",
            {
                "sceneIndex": 0,
                "sceneId": "scene-0",
                "questionId": "q1",
                "response": "12",
                "attemptNumber": 1,
            },
        )
        first = self._record(submitted)
        second = self._record(dict(submitted))
        self.assertEqual(first, second)
        self.assertEqual(self.learning.answer_calls, 1)

    def test_wrong_binding_gap_and_stale_sequence_fail_closed(self):
        with self.assertRaises(ApiError) as wrong:
            self.service.record(
                runtime_session_id="runtime-session-1",
                learning_session_id="learning-session-other",
                upstream_classroom_id="classroom-1",
                data=_event(1, "scene_entered", {"sceneIndex": 0, "sceneId": "scene-0"}),
            )
        self.assertEqual(wrong.exception.code, "runtime_event_session_not_found")

        with self.assertRaises(ApiError) as gap:
            self._record(_event(2, "scene_entered", {"sceneIndex": 0, "sceneId": "scene-0"}))
        self.assertEqual(gap.exception.code, "runtime_event_sequence_gap")

        with self.assertRaises(ApiError) as forged_scene:
            self._record(
                _event(
                    1,
                    "scene_entered",
                    {"sceneIndex": 0, "sceneId": "browser-invented-scene"},
                )
            )
        self.assertEqual(
            forged_scene.exception.code,
            "runtime_event_scene_authority_mismatch",
        )

        self._record(_event(1, "scene_entered", {"sceneIndex": 0, "sceneId": "scene-0"}))
        with self.assertRaises(ApiError) as forged_action:
            self._record(
                _event(
                    2,
                    "action_completed",
                    {
                        "sceneIndex": 0,
                        "sceneId": "scene-0",
                        "actionId": "browser-invented-action",
                    },
                )
            )
        self.assertEqual(
            forged_action.exception.code,
            "runtime_event_action_authority_mismatch",
        )
        with self.assertRaises(ApiError) as stale:
            self._record(_event(1, "scene_entered", {"sceneIndex": 0, "sceneId": "changed"}))
        self.assertEqual(stale.exception.code, "runtime_event_sequence_conflict")

    def test_record_uses_child_first_global_write_lock_order(self):
        self._record(
            _event(1, "scene_entered", {"sceneIndex": 0, "sceneId": "scene-0"})
        )

        self.assertEqual(
            self.repository.lock_calls,
            [
                "runtime_subject_snapshot",
                "child",
                "principal",
                "task",
                "learning_session",
                "formal_pointer",
                "formal_plan",
                "formal_history",
                "formal_course_ownership",
                "runtime_authority",
                "runtime_stream",
            ],
        )

    def test_answer_fails_closed_after_grade_switch_without_any_write(self):
        self.repository.child["grade_code"] = "primary_2"
        self.repository.child["grade_selection_revision"] = 2

        with self.assertRaises(ApiError) as raised:
            self._record(
                _event(
                    1,
                    "answer_submitted",
                    {
                        "sceneIndex": 0,
                        "sceneId": "scene-0",
                        "questionId": "q1",
                        "response": "12",
                        "attemptNumber": 1,
                    },
                )
            )

        self.assertEqual(raised.exception.code, "student_learning_grade_not_open")
        self.assertEqual(self.learning.answer_calls, 0)
        self.assertEqual(self.learning.complete_calls, 0)
        self.assertEqual(self.repository.events, [])
        self.assertIsNone(self.repository.stream)

    def test_answer_fails_closed_after_revision_drift_without_any_write(self):
        self.repository.child["grade_selection_revision"] = 2
        self.repository.plan = None

        with self.assertRaises(ApiError) as raised:
            self._record(
                _event(
                    1,
                    "answer_submitted",
                    {
                        "sceneIndex": 0,
                        "sceneId": "scene-0",
                        "questionId": "q1",
                        "response": "12",
                        "attemptNumber": 1,
                    },
                )
            )

        self.assertEqual(raised.exception.code, "student_learning_release_not_ready")
        self.assertEqual(self.learning.answer_calls, 0)
        self.assertEqual(self.repository.events, [])
        self.assertIsNone(self.repository.stream)

    def test_completion_fails_closed_when_principal_no_longer_owns_child(self):
        self.repository.principal["child_id"] = "child-other"

        with self.assertRaises(ApiError) as raised:
            self._record(
                _event(
                    1,
                    "classroom_completed",
                    {"sceneIndex": 9, "sceneId": "scene-9"},
                )
            )

        self.assertEqual(raised.exception.code, "runtime_event_session_not_found")
        self.assertEqual(self.learning.answer_calls, 0)
        self.assertEqual(self.learning.complete_calls, 0)
        self.assertEqual(self.repository.events, [])
        self.assertIsNone(self.repository.stream)

    def test_answer_rejects_course_outside_the_current_formal_release(self):
        self.repository.course_ownership["course_id"] = "course-other"

        with self.assertRaises(ApiError) as raised:
            self._record(
                _event(
                    1,
                    "answer_submitted",
                    {
                        "sceneIndex": 0,
                        "sceneId": "scene-0",
                        "questionId": "q1",
                        "response": "12",
                        "attemptNumber": 1,
                    },
                )
            )

        self.assertEqual(raised.exception.code, "student_learning_release_not_ready")
        self.assertEqual(self.learning.answer_calls, 0)
        self.assertEqual(self.repository.events, [])
        self.assertIsNone(self.repository.stream)

    def test_completion_requires_all_scene_actions_and_questions_and_reports_once(self):
        sequence = 1
        for scene_index in range(10):
            self._record(
                _event(
                    sequence,
                    "scene_entered",
                    {"sceneIndex": scene_index, "sceneId": f"scene-{scene_index}"},
                )
            )
            sequence += 1
            if scene_index < 9:
                self._record(
                    _event(
                        sequence,
                        "action_completed",
                        {
                            "sceneIndex": scene_index,
                            "sceneId": f"scene-{scene_index}",
                            "actionId": f"action-{scene_index}",
                        },
                    )
                )
                sequence += 1

        premature = _event(
            sequence,
            "classroom_completed",
            {"sceneIndex": 9, "sceneId": "scene-9"},
        )
        with self.assertRaises(ApiError) as incomplete:
            self._record(premature)
        self.assertEqual(incomplete.exception.code, "runtime_event_evidence_incomplete")
        self.assertEqual(self.learning.complete_calls, 0)

        self._record(
            _event(
                sequence,
                "action_completed",
                {"sceneIndex": 9, "sceneId": "scene-9", "actionId": "action-9"},
            )
        )
        sequence += 1
        self._record(
            _event(
                sequence,
                "answer_submitted",
                {
                    "sceneIndex": 0,
                    "sceneId": "scene-0",
                    "questionId": "q1",
                    "response": "12",
                    "attemptNumber": 1,
                },
            )
        )
        sequence += 1
        ready = self.service.status(
            runtime_session_id="runtime-session-1",
            learning_session_id="learning-session-1",
            upstream_classroom_id="classroom-1",
        )
        self.assertEqual(ready["sceneEnteredCount"], 10)
        self.assertEqual(ready["actionCompletedSceneCount"], 10)
        self.assertTrue(ready["questionsComplete"])
        self.assertTrue(ready["completionReady"])
        completion = _event(
            sequence,
            "classroom_completed",
            {"sceneIndex": 9, "sceneId": "scene-9"},
        )
        first = self._record(completion)
        second = self._record(dict(completion))
        self.assertTrue(first["completed"])
        self.assertEqual(first["reportId"], "report-1")
        self.assertEqual(first, second)
        self.assertEqual(self.learning.complete_calls, 1)
        self.assertEqual(
            self.task_runtime.completed,
            [("family-1", "task-1")],
        )

        with self.assertRaises(ApiError) as after_completion:
            self._record(
                _event(
                    sequence + 1,
                    "scene_entered",
                    {"sceneIndex": 9, "sceneId": "scene-9"},
                )
            )
        self.assertEqual(
            after_completion.exception.code,
            "runtime_event_stream_completed",
        )
        self.assertEqual(self.learning.complete_calls, 1)

    def test_completion_aggregates_verified_actions_across_runtime_reentry(self):
        self.repository.prior_scene_indices = set(range(10))
        self.repository.prior_action_scene_indices = set(range(9))
        self.learning.answered_question_ids = ["q1"]
        self.learning.questions_complete = True

        sequence = 1
        for scene_index in range(10):
            self._record(
                _event(
                    sequence,
                    "scene_entered",
                    {"sceneIndex": scene_index, "sceneId": f"scene-{scene_index}"},
                )
            )
            sequence += 1
        self._record(
            _event(
                sequence,
                "action_completed",
                {
                    "sceneIndex": 9,
                    "sceneId": "scene-9",
                    "actionId": "action-9",
                },
            )
        )
        sequence += 1

        ready = self.service.status(
            runtime_session_id="runtime-session-1",
            learning_session_id="learning-session-1",
            upstream_classroom_id="classroom-1",
        )
        self.assertEqual(ready["sceneEnteredCount"], 10)
        self.assertEqual(ready["actionCompletedSceneCount"], 10)
        self.assertEqual(ready["answeredQuestionIds"], ["q1"])
        self.assertTrue(ready["completionReady"])

        completed = self._record(
            _event(
                sequence,
                "classroom_completed",
                {"sceneIndex": 9, "sceneId": "scene-9"},
            )
        )
        self.assertTrue(completed["completed"])
        self.assertEqual(completed["reportId"], "report-1")
        self.assertEqual(self.learning.complete_calls, 1)


if __name__ == "__main__":
    unittest.main()
