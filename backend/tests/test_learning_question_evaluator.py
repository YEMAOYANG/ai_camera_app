from __future__ import annotations

import unittest

from services.learning_question_evaluator import (
    EVALUATOR_VERSION,
    LearningQuestionEvaluator,
    STATUS_CORRECT,
    STATUS_INCORRECT,
    STATUS_UNSUPPORTED,
)


class LearningQuestionEvaluatorTest(unittest.TestCase):
    def setUp(self):
        self.evaluator = LearningQuestionEvaluator()

    def test_numeric_uses_nfkc_and_exact_decimal_comparison(self):
        question = {
            "type": "numeric",
            "answer": "12.50",
            "evaluation": {
                "normalization": ["trim", "remove_grouping_separators"]
            },
        }
        result = self.evaluator.evaluate(question, {"value": " １２．５００ "})
        self.assertEqual(result["status"], STATUS_CORRECT)
        self.assertTrue(result["correct"])
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["normalizedResponse"], "12.500")
        self.assertEqual(result["evaluatorVersion"], EVALUATOR_VERSION)

        wrong = self.evaluator.evaluate(question, "12.51")
        self.assertEqual(wrong["status"], STATUS_INCORRECT)
        self.assertFalse(wrong["correct"])

    def test_exact_text_is_strict_unless_normalization_is_declared(self):
        strict = {
            "type": "exact_text",
            "evaluation": {"expected": "Hello, Mira!"},
        }
        self.assertEqual(
            self.evaluator.evaluate(strict, "ＨＥＬＬＯ， ＭＩＲＡ！")["status"],
            STATUS_INCORRECT,
        )

        declared = {
            "type": "exact_text",
            "evaluation": {
                "expected": "Hello, Mira!",
                "normalization": {
                    "operations": [
                        "trim",
                        "collapse_whitespace",
                        "casefold",
                        "strip_punctuation",
                        "remove_whitespace",
                    ]
                },
            },
        }
        result = self.evaluator.evaluate(declared, " ＨＥＬＬＯ，　ＭＩＲＡ！ ")
        self.assertEqual(result["status"], STATUS_CORRECT)
        self.assertEqual(result["normalizedResponse"], "hellomira")

    def test_accepted_text_compares_only_with_declared_answer_set(self):
        question = {
            "type": "accepted_text",
            "evaluation": {
                "acceptedAnswers": ["中华人民共和国", "中国"],
                "normalization": ["trim", "remove_whitespace"],
            },
        }
        result = self.evaluator.evaluate(question, "中 国")
        self.assertEqual(result["status"], STATUS_CORRECT)
        self.assertEqual(result["normalizedResponse"], "中国")
        self.assertEqual(
            self.evaluator.evaluate(question, "中华")["status"],
            STATUS_INCORRECT,
        )

    def test_single_choice_uses_option_id_not_label_or_position(self):
        question = {
            "type": "single_choice",
            "choices": [
                {"id": "noun", "label": "名词"},
                {"id": "verb", "label": "动词"},
            ],
            "evaluation": {"expectedOptionId": "verb"},
        }
        self.assertEqual(
            self.evaluator.evaluate(question, {"optionId": "verb"})["status"],
            STATUS_CORRECT,
        )
        self.assertEqual(
            self.evaluator.evaluate(question, "动词")["status"],
            STATUS_INCORRECT,
        )

    def test_sequence_requires_an_explicit_list_and_preserves_order(self):
        question = {
            "type": "sequence",
            "evaluation": {
                "expectedSequence": ["first", "second", "third"],
                "normalization": ["trim", "casefold"],
            },
        }
        correct = self.evaluator.evaluate(
            question, {"items": [" FIRST ", "Second", "THIRD"]}
        )
        self.assertEqual(correct["status"], STATUS_CORRECT)
        self.assertEqual(
            self.evaluator.evaluate(
                question, {"items": ["second", "first", "third"]}
            )["status"],
            STATUS_INCORRECT,
        )
        self.assertEqual(
            self.evaluator.evaluate(question, "first,second,third")["status"],
            STATUS_INCORRECT,
        )

    def test_unknown_question_type_and_invalid_authority_are_unsupported(self):
        unknown = self.evaluator.evaluate(
            {"type": "llm_rubric", "evaluation": {"prompt": "judge it"}},
            "free response",
        )
        self.assertEqual(unknown["status"], STATUS_UNSUPPORTED)
        self.assertEqual(unknown["reason"], "unsupported_question_type")

        participation = self.evaluator.evaluate(
            {"type": "participation"}, {"completed": True}
        )
        self.assertEqual(participation["status"], STATUS_UNSUPPORTED)
        self.assertEqual(participation["reason"], "unsupported_question_type")

        missing_answer = self.evaluator.evaluate(
            {"type": "exact_text"},
            "anything",
        )
        self.assertEqual(missing_answer["status"], STATUS_UNSUPPORTED)
        self.assertEqual(missing_answer["reason"], "missing_expected_answer")

    def test_normalization_rejects_regex_script_and_unknown_operations(self):
        dangerous_contracts = (
            {"regex": "^answer$"},
            {"operations": ["trim", "__import__('os').system('unsafe')"]},
            ["trim", "regex_replace"],
        )
        for index, normalization in enumerate(dangerous_contracts):
            with self.subTest(index=index):
                result = self.evaluator.evaluate(
                    {
                        "type": "exact_text",
                        "evaluation": {
                            "expected": "answer",
                            "normalization": normalization,
                        },
                    },
                    "answer",
                )
                self.assertEqual(result["status"], STATUS_UNSUPPORTED)
                self.assertEqual(result["reason"], "unsupported_normalization")


if __name__ == "__main__":
    unittest.main()
