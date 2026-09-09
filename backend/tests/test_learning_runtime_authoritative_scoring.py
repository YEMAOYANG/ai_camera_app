from __future__ import annotations

import json
import unittest

from core.errors import ApiError
from services.learning_question_evaluator import LearningQuestionEvaluator
from services.learning_service import LearningService


NOW = 1_777_777_777_000


def _question(question_id: str, answer: str) -> dict:
    return {
        "id": question_id,
        "type": "numeric",
        "prompt": f"{question_id} 的答案",
        "answer": answer,
        "skill": "number_sense_20",
        "hint": "数一数",
        "explanation": "按位计算",
        "verificationExpression": answer,
        "evaluation": {"expected": answer, "normalization": ["trim"]},
    }


QUESTIONS = [_question(f"q{index}", str(10 + index)) for index in range(1, 5)]
COURSE_CONTENT = {
    "questions": QUESTIONS,
    "teachingFlow": {
        "schemaVersion": "mira.learning.teaching-flow.v1",
        "guidedQuestionIds": ["q1", "q2"],
        "independentQuestionIds": ["q3", "q4"],
    },
}


def _authority(
    *,
    question_index: int = 0,
    answers: list[dict] | None = None,
    correct_count: int = 0,
    attempted_count: int = 0,
    status: str = "in_progress",
) -> dict:
    return {
        "family_id": "family-1",
        "child_id": "child-1",
        "learning_session_id": "learning-session-1",
        "session_task_id": "task-1",
        "session_course_id": "course-1",
        "session_course_version": "1",
        "session_status": status,
        "session_current_question_index": question_index,
        "session_correct_count": correct_count,
        "session_attempted_count": attempted_count,
        "session_answers_json": json.dumps(answers or []),
        "session_started_at": NOW - 10_000,
        "course_content_json": json.dumps(COURSE_CONTENT),
        "course_grade_code": "primary_1",
        "course_subject": "math",
        "course_node_code": "number_sense_20",
        "course_title": "20以内数的认识",
        "course_objective": "掌握数的组成",
    }


class _Repository:
    def __init__(self):
        self.updated = []
        self.events = []

    @staticmethod
    def parse_json(value, fallback):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return fallback

    def update_session(self, _conn, **kwargs):
        self.updated.append(dict(kwargs))
        return {
            "id": kwargs["session_id"],
            "family_id": kwargs["family_id"],
            "child_id": "child-1",
            "task_id": "task-1",
            "course_id": "course-1",
            "course_version": "1",
            "status": kwargs["status"],
            "current_question_index": kwargs["current_question_index"],
            "correct_count": kwargs["correct_count"],
            "attempted_count": kwargs["attempted_count"],
            "answers_json": json.dumps(kwargs["answers"]),
            "started_at": NOW - 10_000,
            "completed_at": kwargs["completed_at"],
        }

    def add_task_event(self, _conn, **kwargs):
        self.events.append(dict(kwargs))


class LearningRuntimeAuthoritativeScoringTest(unittest.TestCase):
    def setUp(self):
        self.repository = _Repository()
        self.service = LearningService.__new__(LearningService)
        self.service.repository = self.repository
        self.service.question_evaluator = LearningQuestionEvaluator()
        self.service.static_catalog_enabled = False

    def test_answer_uses_mira_evaluator_and_rejects_question_or_attempt_forgery(self):
        with self.assertRaises(ApiError) as wrong_question:
            self.service.record_authoritative_runtime_answer(
                object(),
                authority=_authority(),
                question_id="q2",
                submitted_answer="12",
                attempt_number=1,
                now=NOW,
            )
        self.assertEqual(wrong_question.exception.code, "runtime_answer_question_conflict")

        with self.assertRaises(ApiError) as wrong_attempt:
            self.service.record_authoritative_runtime_answer(
                object(),
                authority=_authority(),
                question_id="q1",
                submitted_answer="11",
                attempt_number=2,
                now=NOW,
            )
        self.assertEqual(wrong_attempt.exception.code, "runtime_answer_attempt_conflict")

        result = self.service.record_authoritative_runtime_answer(
            object(),
            authority=_authority(),
            question_id="q1",
            submitted_answer="11",
            attempt_number=1,
            now=NOW,
        )
        self.assertTrue(result["correct"])
        self.assertEqual(result["evaluatorVersion"], "mira.learning.question-evaluator.v1")
        self.assertEqual(self.repository.updated[-1]["status"], "in_progress")
        self.assertNotIn("score", result)

    def test_first_wrong_answer_advances_so_the_second_question_in_the_scene_is_accepted(self):
        first = self.service.record_authoritative_runtime_answer(
            object(),
            authority=_authority(),
            question_id="q1",
            submitted_answer="99",
            attempt_number=1,
            now=NOW,
        )
        first_update = self.repository.updated[-1]
        self.assertFalse(first["correct"])
        self.assertEqual(first_update["current_question_index"], 1)
        self.assertEqual(first_update["attempted_count"], 1)

        second = self.service.record_authoritative_runtime_answer(
            object(),
            authority=_authority(
                question_index=first_update["current_question_index"],
                answers=first_update["answers"],
                correct_count=first_update["correct_count"],
                attempted_count=first_update["attempted_count"],
            ),
            question_id="q2",
            submitted_answer="12",
            attempt_number=1,
            now=NOW + 1,
        )
        self.assertTrue(second["correct"])
        self.assertEqual(self.repository.updated[-1]["current_question_index"], 2)
        self.assertEqual(self.repository.updated[-1]["attempted_count"], 2)

    def test_final_answer_does_not_publish_report_before_classroom_completion(self):
        prior_answers = [
            {
                "questionId": f"q{index}",
                "questionIndex": index - 1,
                "answer": str(10 + index),
                "normalizedResponse": str(10 + index),
                "evaluatorVersion": "mira.learning.question-evaluator.v1",
                "correct": True,
                "attemptNumber": 1,
                "answeredAt": NOW - 1000 + index,
            }
            for index in range(1, 4)
        ]
        result = self.service.record_authoritative_runtime_answer(
            object(),
            authority=_authority(
                question_index=3,
                answers=prior_answers,
                correct_count=3,
                attempted_count=3,
            ),
            question_id="q4",
            submitted_answer="14",
            attempt_number=1,
            now=NOW,
        )
        self.assertTrue(result["questionsComplete"])
        self.assertEqual(self.repository.updated[-1]["status"], "in_progress")
        self.assertIsNone(self.repository.updated[-1]["completed_at"])

    def test_answered_question_ids_are_authoritative_across_runtime_reentry(self):
        answers = [
            {"questionId": "q3"},
            {"questionId": "browser-invented-question"},
            {"questionId": "q1"},
            {"questionId": "q1"},
        ]

        answered = self.service.authoritative_runtime_answered_question_ids(
            object(),
            authority=_authority(
                question_index=2,
                answers=answers,
                attempted_count=2,
            ),
        )

        self.assertEqual(answered, ["q1", "q3"])

    def test_completion_marks_session_then_calls_existing_report_path_once(self):
        answers = [
            {
                "questionId": f"q{index}",
                "questionIndex": index - 1,
                "answer": str(10 + index),
                "normalizedResponse": str(10 + index),
                "evaluatorVersion": "mira.learning.question-evaluator.v1",
                "correct": True,
                "attemptNumber": 1,
                "answeredAt": NOW - 1000 + index,
            }
            for index in range(1, 5)
        ]
        report_calls = []

        def complete(_conn, *, session, course, questions, answers, now):
            report_calls.append((session, course, questions, answers, now))
            return {"id": "report-1"}

        self.service._complete_and_report = complete
        report = self.service.complete_authoritative_runtime_session(
            object(),
            authority=_authority(
                question_index=4,
                answers=answers,
                correct_count=4,
                attempted_count=4,
            ),
            now=NOW,
        )
        self.assertEqual(report["id"], "report-1")
        self.assertEqual(self.repository.updated[-1]["status"], "completed")
        self.assertEqual(self.repository.updated[-1]["completed_at"], NOW)
        self.assertEqual(len(report_calls), 1)

        with self.assertRaises(ApiError) as already_complete:
            self.service.complete_authoritative_runtime_session(
                object(),
                authority=_authority(
                    question_index=4,
                    answers=answers,
                    correct_count=4,
                    attempted_count=4,
                    status="completed",
                ),
                now=NOW,
            )
        self.assertEqual(already_complete.exception.code, "runtime_learning_already_completed")
        self.assertEqual(len(report_calls), 1)


if __name__ == "__main__":
    unittest.main()
