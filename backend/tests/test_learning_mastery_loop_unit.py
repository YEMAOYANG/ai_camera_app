from __future__ import annotations

import json
import unittest

from services.learning_question_evaluator import LearningQuestionEvaluator
from services.learning_service import LearningService


def _question(question_id: str) -> dict:
    return {
        "id": question_id,
        "type": "numeric",
        "prompt": f"{question_id} 的答案",
        "answer": "1",
        "skill": "number_sense_20",
        "hint": "数一数",
        "explanation": "再按顺序数一次。",
        "evaluation": {"expected": "1", "normalization": ["trim"]},
    }


QUESTIONS = [_question(f"q{index}") for index in range(1, 6)]
CONTENT = {
    "questions": QUESTIONS,
    "teachingFlow": {
        "schemaVersion": "mira.learning.teaching-flow.v1",
        "demoQuestionId": "q1",
        "guidedQuestionIds": ["q2", "q3"],
        "independentQuestionIds": ["q4", "q5"],
    },
}


class _Repository:
    def __init__(self) -> None:
        self.report_args = None
        self.mastery_args = None

    @staticmethod
    def parse_json(value, fallback):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def has_unpracticed_course(*_args, **_kwargs):
        return True

    def create_or_get_report(self, _conn, **kwargs):
        self.report_args = kwargs
        return {"id": "report-1", **kwargs}

    def upsert_mastery_state(self, _conn, **kwargs):
        self.mastery_args = kwargs

    @staticmethod
    def mark_task_completed(*_args, **_kwargs):
        return None

    @staticmethod
    def add_task_event(*_args, **_kwargs):
        return None

    @staticmethod
    def get_task(*_args, **_kwargs):
        return {"scheduled_date": "2026-09-01"}


class LearningMasteryLoopUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = _Repository()
        self.service = LearningService.__new__(LearningService)
        self.service.repository = self.repository
        self.service.question_evaluator = LearningQuestionEvaluator()
        self.service.static_catalog_enabled = False
        self.course = {
            "id": "course-1",
            "version": "1",
            "grade_code": "primary_1",
            "subject": "math",
            "node_code": "number_sense_20",
            "content_json": json.dumps(CONTENT),
        }

    def test_only_verified_practice_questions_block_until_correct(self):
        self.assertFalse(
            self.service._teaching_flow_requires_correct_answer(
                self.course, question_id="q1"
            )
        )
        for question_id in ("q2", "q3", "q4", "q5"):
            self.assertTrue(
                self.service._teaching_flow_requires_correct_answer(
                    self.course, question_id=question_id
                )
            )

    def test_corrected_independent_answers_close_the_mastery_loop(self):
        runtime_questions = QUESTIONS[1:]
        answers = [
            {"questionId": "q2", "attemptNumber": 1, "correct": True},
            {"questionId": "q3", "attemptNumber": 1, "correct": True},
            {"questionId": "q4", "attemptNumber": 1, "correct": False},
            {"questionId": "q4", "attemptNumber": 2, "correct": True},
            {"questionId": "q5", "attemptNumber": 1, "correct": True},
        ]
        session = {
            "id": "session-1",
            "family_id": "family-1",
            "child_id": "child-1",
            "task_id": "task-1",
            "attempted_count": len(answers),
            "correct_count": 4,
        }

        self.service._complete_and_report(
            object(),
            session=session,
            course=self.course,
            questions=runtime_questions,
            answers=answers,
            now=1_000,
        )

        self.assertEqual(self.repository.report_args["score"], 50)
        self.assertEqual(
            self.repository.report_args["independent_correct_count"], 1
        )
        self.assertEqual(self.repository.report_args["mastery_level"], "mastered")
        self.assertIn("当堂闭环", self.repository.report_args["summary"])
        self.assertEqual(self.repository.mastery_args["mastery_level"], "mastered")
        self.assertEqual(self.repository.mastery_args["next_review_date"], "2026-09-08")


if __name__ == "__main__":
    unittest.main()
