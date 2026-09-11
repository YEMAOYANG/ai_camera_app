from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import Mock, patch
from core.errors import ApiError
from services.openmaic_runtime_event_service import OpenMaicRuntimeEventService
from tests.test_openmaic_runtime_event_bridge import _Repository, _LearningService, _event, NOW
from tests.test_openmaic_formal_interaction import interaction_fixture


class RuntimeInteractionTest(unittest.TestCase):
    def setUp(self):
        self.repo, self.learning = _Repository(), _LearningService()
        self.service = OpenMaicRuntimeEventService(repository=self.repo, learning_service=self.learning, clock=lambda: NOW)
        self.objective = {"objectiveIndex": 0, "demonstration": {"sceneId": "scene-0", "quote": "老师示范"},
            "operation": {"sceneId": "scene-5", "controlSelector": "#quantity", "action": "range", "value": "12"},
            "feedback": {"sceneId": "scene-5", "selector": "#result", "textIncludes": "一个十两个一", "reasonQuote": "十个一是一个十"},
            "independentJudgment": {"sceneId": "scene-6", "questionId": "q4"}}
        self.payload = {"sceneIndex": 5, "sceneId": "scene-5", "objectiveIndex": 0, "controlSelector": "#quantity",
                        "action": "range", "value": "12", "feedbackText": "一个十两个一，因为十个一是一个十"}
        self.repo.learning_session_interaction_evidence = lambda conn, **kwargs: [row for row in self.repo.events if row["event_type"] == "interaction_completed"]
        self.policy = patch.object(self.service, "_interaction_objectives", return_value=[self.objective])
        self.policy.start()
        self.addCleanup(self.policy.stop)
        self.repo.scene_ids = {i: f"scene-{i}" for i in range(10)}
        self.repo.action_scene_indices = set(range(10))

    def record(self, kind, payload, sequence=1):
        return self.service.record(runtime_session_id="runtime-session-1", learning_session_id="learning-session-1",
            upstream_classroom_id="classroom-1", data=_event(sequence, kind, payload))

    def test_published_qa_receipt_is_not_student_completion(self):
        self.learning.questions_complete = True
        with self.assertRaises(ApiError) as error:
            self.record("classroom_completed", {"sceneIndex": 9, "sceneId": "scene-9"})
        self.assertEqual(error.exception.code, "runtime_event_evidence_incomplete")
        self.assertEqual(self.learning.complete_calls, 0)
        self.record("interaction_completed", self.payload)
        self.assertTrue(self.record("classroom_completed", {"sceneIndex": 9, "sceneId": "scene-9"}, 2)["completed"])
        self.assertEqual(self.learning.complete_calls, 1)

    def test_independent_judgment_requires_operation_and_exact_replay_is_idempotent(self):
        answer = {"sceneIndex": 6, "sceneId": "scene-6", "questionId": "q4", "response": "12", "attemptNumber": 1}
        with self.assertRaises(ApiError) as error:
            self.record("answer_submitted", answer)
        self.assertEqual(error.exception.code, "runtime_event_interaction_incomplete")
        first = self.record("interaction_completed", self.payload)
        self.assertEqual(first, self.record("interaction_completed", self.payload))
        self.record("answer_submitted", answer, 2)
        self.assertEqual(self.learning.answer_calls, 1)
        status = self.service.status(runtime_session_id="runtime-session-1", learning_session_id="learning-session-1", upstream_classroom_id="classroom-1")
        self.assertEqual(status["completedInteractionObjectiveIndexes"], [0])

    def test_wrong_scene_value_selector_and_decorative_feedback_fail_without_write(self):
        for changed in [{"objectiveIndex": 1}, {"sceneId": "scene-4", "sceneIndex": 4}, {"value": "10"},
                        {"controlSelector": "#another"}, {"feedbackText": "答对了！"}]:
            with self.subTest(changed=changed), self.assertRaises(ApiError):
                self.record("interaction_completed", {**self.payload, **changed})
        self.assertEqual(self.repo.events, [])

    def test_malformed_payload_cannot_claim_success_or_score(self):
        for changed in [{"objectiveIndex": True}, {"objectiveIndex": 30}, {"action": "evaluate"},
                        {"value": "x" * 501}, {"controlSelector": "body *"}, {"feedbackText": ""}, {"passed": True}]:
            with self.subTest(changed=changed), self.assertRaises(ApiError):
                self.record("interaction_completed", {**self.payload, **changed})

    def test_frozen_manifest_is_validated_and_cannot_lose_new_receipt(self):
        manifest, classroom = interaction_fixture()
        authority = {"feature_manifest_json": manifest, "upstream_classroom_id": classroom["stage"]["id"]}
        self.assertTrue(OpenMaicRuntimeEventService._interaction_objectives(authority))
        tampered = deepcopy(authority)
        del tampered["feature_manifest_json"]["professionalCreation"]["interactionDesign"]
        with self.assertRaises(ApiError):
            OpenMaicRuntimeEventService._interaction_objectives(tampered)
        self.assertEqual(OpenMaicRuntimeEventService._interaction_objectives(self.repo.authority), [])

    def test_completed_session_closes_only_its_two_frozen_budget_scopes(self):
        from services.learning_paid_authority import scope_digest, teaching_budget_scope
        manifest, _ = interaction_fixture()
        budget = Mock()
        self.service.budget_service = budget
        authority = {**self.repo.authority, "feature_manifest_json": manifest}
        self.service._close_completed_budget(authority)
        row = {**authority, "course_id": authority["session_course_id"], "course_version": authority["session_course_version"]}
        self.assertEqual(budget.close_authorization.call_count, 2)
        self.assertEqual([call.kwargs["authorization_id"] for call in budget.close_authorization.call_args_list],
            [scope_digest(teaching_budget_scope(row, manifest, purpose)) for purpose in ("required_teaching", "optional_interaction")])
        budget.reset_mock()
        self.service._close_completed_budget(self.repo.authority)
        budget.close_authorization.assert_not_called()

    def test_budget_outage_does_not_undo_completion_and_status_retries_release(self):
        self.learning.questions_complete = True
        self.record("interaction_completed", self.payload)
        with patch.object(self.service, "_close_completed_budget") as close:
            self.record("classroom_completed", {"sceneIndex": 9, "sceneId": "scene-9"}, 2)
            self.assertEqual(self.learning.complete_calls, 1)
            close.assert_called_once()
            self.service.status(runtime_session_id="runtime-session-1", learning_session_id="learning-session-1", upstream_classroom_id="classroom-1")
            self.assertEqual(close.call_count, 2)
        manifest, _ = interaction_fixture()
        budget = Mock()
        budget.close_authorization.side_effect = ApiError("budget_outage", "Unavailable", 503)
        self.service.budget_service = budget
        with self.assertLogs("services.openmaic_runtime_event_service", level="WARNING"):
            self.service._close_completed_budget({**self.repo.authority, "feature_manifest_json": manifest})
        self.assertEqual(budget.close_authorization.call_count, 2)
        self.assertEqual(self.learning.complete_calls, 1)
