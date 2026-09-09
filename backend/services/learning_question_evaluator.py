from __future__ import annotations

import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence


EVALUATOR_VERSION = "mira.learning.question-evaluator.v1"

STATUS_CORRECT = "correct"
STATUS_INCORRECT = "incorrect"
STATUS_UNSUPPORTED = "unsupported"

SCORED_DETERMINISTIC_TYPES = frozenset(
    {
        "numeric",
        "exact_text",
        "accepted_text",
        "single_choice",
        "sequence",
    }
)
SUPPORTED_QUESTION_TYPES = SCORED_DETERMINISTIC_TYPES

_SUPPORTED_NORMALIZATION_OPERATIONS = frozenset(
    {
        "trim",
        "collapse_whitespace",
        "remove_whitespace",
        "casefold",
        "strip_terminal_punctuation",
        "strip_punctuation",
        "remove_grouping_separators",
    }
)
_NORMALIZATION_OPERATIONS_BY_TYPE = {
    "numeric": frozenset({"trim", "remove_grouping_separators"}),
    "exact_text": _SUPPORTED_NORMALIZATION_OPERATIONS
    - {"remove_grouping_separators"},
    "accepted_text": _SUPPORTED_NORMALIZATION_OPERATIONS
    - {"remove_grouping_separators"},
    "single_choice": frozenset({"trim", "casefold"}),
    "sequence": _SUPPORTED_NORMALIZATION_OPERATIONS
    - {"remove_grouping_separators"},
}
_TERMINAL_PUNCTUATION = frozenset(".!?;:。！？；：")
_MISSING = object()


class LearningQuestionEvaluator:
    """Evaluates only explicitly supported, deterministic response contracts.

    Unicode NFKC normalization is mandatory. Every additional normalization is
    selected from a closed declarative list; content cannot provide regular
    expressions, code, function names, or scripts.
    """

    version = EVALUATOR_VERSION

    def supports(self, question_type: str) -> bool:
        return str(question_type or "").strip() in SUPPORTED_QUESTION_TYPES

    def is_scored_deterministic(self, question_type: str) -> bool:
        return str(question_type or "").strip() in SCORED_DETERMINISTIC_TYPES

    def evaluate(
        self,
        question: Mapping[str, Any],
        response: Any,
    ) -> dict[str, Any]:
        if not isinstance(question, Mapping):
            return self._unsupported("invalid_question")

        question_type = str(question.get("type") or "").strip()
        if question_type not in SUPPORTED_QUESTION_TYPES:
            return self._unsupported("unsupported_question_type", question_type)

        evaluation = question.get("evaluation")
        if evaluation is None:
            evaluation = {}
        if not isinstance(evaluation, Mapping):
            return self._unsupported("invalid_evaluation_contract", question_type)

        operations = self._normalization_operations(question, evaluation)
        if operations is None or not set(operations).issubset(
            _NORMALIZATION_OPERATIONS_BY_TYPE[question_type]
        ):
            return self._unsupported("unsupported_normalization", question_type)

        if question_type == "numeric":
            return self._evaluate_numeric(question, evaluation, response, operations)
        if question_type == "exact_text":
            return self._evaluate_exact_text(question, evaluation, response, operations)
        if question_type == "accepted_text":
            return self._evaluate_accepted_text(
                question, evaluation, response, operations
            )
        if question_type == "single_choice":
            return self._evaluate_single_choice(
                question, evaluation, response, operations
            )
        if question_type == "sequence":
            return self._evaluate_sequence(question, evaluation, response, operations)
        return self._unsupported("unsupported_question_type", question_type)

    def _evaluate_numeric(
        self,
        question: Mapping[str, Any],
        evaluation: Mapping[str, Any],
        response: Any,
        operations: tuple[str, ...],
    ) -> dict[str, Any]:
        expected = self._first_value(
            evaluation,
            ("expected", "expectedAnswer"),
            fallback=question.get("answer", _MISSING),
        )
        if expected is _MISSING or isinstance(expected, (Mapping, list, tuple, set)):
            return self._unsupported("missing_expected_answer", "numeric")

        actual_text = self._scalar_text(self._response_value(response))
        expected_text = self._scalar_text(expected)
        if expected_text is None:
            return self._unsupported("invalid_expected_answer", "numeric")
        if actual_text is None:
            return self._incorrect("numeric", normalized_response=None)
        actual_text = self._normalize_text(actual_text, operations)
        expected_text = self._normalize_text(expected_text, operations)
        try:
            actual_number = Decimal(actual_text)
        except (InvalidOperation, ValueError):
            return self._incorrect("numeric", normalized_response=actual_text)
        try:
            expected_number = Decimal(expected_text)
        except (InvalidOperation, ValueError):
            return self._unsupported("invalid_expected_answer", "numeric")
        return self._scored(
            "numeric",
            actual_number == expected_number,
            normalized_response=str(actual_number),
        )

    def _evaluate_exact_text(
        self,
        question: Mapping[str, Any],
        evaluation: Mapping[str, Any],
        response: Any,
        operations: tuple[str, ...],
    ) -> dict[str, Any]:
        expected = self._first_value(
            evaluation,
            ("expected", "expectedAnswer"),
            fallback=question.get("answer", _MISSING),
        )
        if expected is _MISSING or isinstance(expected, (Mapping, list, tuple, set)):
            return self._unsupported("missing_expected_answer", "exact_text")
        actual_text = self._scalar_text(self._response_value(response))
        expected_text = self._scalar_text(expected)
        if expected_text is None:
            return self._unsupported("invalid_expected_answer", "exact_text")
        if actual_text is None:
            return self._incorrect("exact_text", normalized_response=None)
        actual = self._normalize_text(actual_text, operations)
        wanted = self._normalize_text(expected_text, operations)
        return self._scored(
            "exact_text", actual == wanted, normalized_response=actual
        )

    def _evaluate_accepted_text(
        self,
        question: Mapping[str, Any],
        evaluation: Mapping[str, Any],
        response: Any,
        operations: tuple[str, ...],
    ) -> dict[str, Any]:
        accepted = self._first_value(
            evaluation,
            ("acceptedAnswers", "expectedAnswers"),
            fallback=question.get("acceptedAnswers", _MISSING),
        )
        if accepted is _MISSING:
            legacy = question.get("answer", _MISSING)
            accepted = legacy if isinstance(legacy, (list, tuple)) else _MISSING
        if (
            accepted is _MISSING
            or isinstance(accepted, (str, bytes, Mapping))
            or not isinstance(accepted, Sequence)
            or not accepted
        ):
            return self._unsupported("missing_accepted_answers", "accepted_text")

        normalized_answers: list[str] = []
        for value in accepted:
            text = self._scalar_text(value)
            if text is None:
                return self._unsupported("invalid_accepted_answers", "accepted_text")
            normalized_answers.append(self._normalize_text(text, operations))
        actual_text = self._scalar_text(self._response_value(response))
        if actual_text is None:
            return self._incorrect("accepted_text", normalized_response=None)
        actual = self._normalize_text(actual_text, operations)
        return self._scored(
            "accepted_text",
            actual in set(normalized_answers),
            normalized_response=actual,
        )

    def _evaluate_single_choice(
        self,
        question: Mapping[str, Any],
        evaluation: Mapping[str, Any],
        response: Any,
        operations: tuple[str, ...],
    ) -> dict[str, Any]:
        expected = self._first_value(
            evaluation,
            ("expectedOptionId", "expected", "expectedAnswer"),
            fallback=question.get("answer", _MISSING),
        )
        expected_text = self._scalar_text(expected)
        if expected is _MISSING or expected_text is None:
            return self._unsupported("missing_expected_option", "single_choice")

        options = question.get("choices")
        if options is None:
            options = question.get("options")
        if isinstance(options, list) and options:
            option_ids = {
                self._normalize_text(option_id, operations)
                for option_id in (self._option_id(item) for item in options)
                if option_id is not None
            }
            if (
                not option_ids
                or self._normalize_text(expected_text, operations) not in option_ids
            ):
                return self._unsupported("invalid_expected_option", "single_choice")

        actual_text = self._scalar_text(self._choice_response(response))
        if actual_text is None:
            return self._incorrect("single_choice", normalized_response=None)
        actual = self._normalize_text(actual_text, operations)
        wanted = self._normalize_text(expected_text, operations)
        return self._scored(
            "single_choice", actual == wanted, normalized_response=actual
        )

    def _evaluate_sequence(
        self,
        question: Mapping[str, Any],
        evaluation: Mapping[str, Any],
        response: Any,
        operations: tuple[str, ...],
    ) -> dict[str, Any]:
        expected = self._first_value(
            evaluation,
            ("expectedSequence", "expected"),
            fallback=question.get("answer", _MISSING),
        )
        if (
            expected is _MISSING
            or isinstance(expected, (str, bytes, Mapping))
            or not isinstance(expected, Sequence)
            or not expected
        ):
            return self._unsupported("missing_expected_sequence", "sequence")
        actual_value = self._sequence_response(response)
        if not isinstance(actual_value, list):
            return self._incorrect("sequence", normalized_response=None)
        expected_items = self._normalize_sequence(expected, operations)
        actual_items = self._normalize_sequence(actual_value, operations)
        if expected_items is None:
            return self._unsupported("invalid_expected_sequence", "sequence")
        if actual_items is None:
            return self._incorrect("sequence", normalized_response=None)
        return self._scored(
            "sequence",
            actual_items == expected_items,
            normalized_response=actual_items,
        )

    def _normalization_operations(
        self,
        question: Mapping[str, Any],
        evaluation: Mapping[str, Any],
    ) -> tuple[str, ...] | None:
        raw = evaluation.get("normalization", _MISSING)
        if raw is _MISSING:
            raw = question.get("normalization", _MISSING)
        if raw is _MISSING:
            response_contract = question.get("response")
            if isinstance(response_contract, Mapping):
                raw = response_contract.get("normalization", _MISSING)
        if raw is _MISSING or raw is None:
            return ("trim",)
        if isinstance(raw, Mapping):
            if set(raw.keys()) != {"operations"}:
                return None
            raw = raw.get("operations")
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, (list, tuple)):
            return None
        operations: list[str] = []
        for value in raw:
            operation = str(value or "").strip()
            if operation not in _SUPPORTED_NORMALIZATION_OPERATIONS:
                return None
            if operation not in operations:
                operations.append(operation)
        return tuple(operations)

    @staticmethod
    def _normalize_text(value: str, operations: tuple[str, ...]) -> str:
        result = unicodedata.normalize("NFKC", value)
        for operation in operations:
            if operation == "trim":
                result = result.strip()
            elif operation == "collapse_whitespace":
                result = " ".join(result.split())
            elif operation == "remove_whitespace":
                result = "".join(char for char in result if not char.isspace())
            elif operation == "casefold":
                result = result.casefold()
            elif operation == "strip_terminal_punctuation":
                result = result.rstrip("".join(_TERMINAL_PUNCTUATION)).rstrip()
            elif operation == "strip_punctuation":
                result = "".join(
                    char
                    for char in result
                    if not unicodedata.category(char).startswith("P")
                )
            elif operation == "remove_grouping_separators":
                result = result.replace(",", "")
        return result

    def _normalize_sequence(
        self, values: Sequence[Any], operations: tuple[str, ...]
    ) -> list[str] | None:
        normalized: list[str] = []
        for value in values:
            text = self._scalar_text(value)
            if text is None:
                return None
            normalized.append(self._normalize_text(text, operations))
        return normalized

    @staticmethod
    def _first_value(
        source: Mapping[str, Any], keys: tuple[str, ...], *, fallback: Any
    ) -> Any:
        for key in keys:
            if key in source:
                return source[key]
        return fallback

    @staticmethod
    def _scalar_text(value: Any) -> str | None:
        if value is None or isinstance(value, (bool, Mapping, list, tuple, set)):
            return None
        if isinstance(value, (str, int, float, Decimal)):
            return str(value)
        return None

    @staticmethod
    def _response_value(response: Any) -> Any:
        if not isinstance(response, Mapping):
            return response
        for key in ("value", "answer", "text"):
            if key in response:
                return response[key]
        return None

    @staticmethod
    def _choice_response(response: Any) -> Any:
        if not isinstance(response, Mapping):
            return response
        for key in ("optionId", "value", "answer"):
            if key in response:
                return response[key]
        return None

    @staticmethod
    def _sequence_response(response: Any) -> Any:
        if isinstance(response, list):
            return response
        if isinstance(response, Mapping):
            value = response.get("items", response.get("value"))
            return value if isinstance(value, list) else None
        return None

    @staticmethod
    def _option_id(option: Any) -> str | None:
        if isinstance(option, Mapping):
            for key in ("id", "value"):
                value = option.get(key)
                if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                    return str(value)
            return None
        if isinstance(option, (str, int, float)) and not isinstance(option, bool):
            return str(option)
        return None

    def _scored(
        self,
        question_type: str,
        correct: bool,
        *,
        normalized_response: Any,
    ) -> dict[str, Any]:
        return {
            "status": STATUS_CORRECT if correct else STATUS_INCORRECT,
            "correct": bool(correct),
            "score": 100 if correct else 0,
            "questionType": question_type,
            "evaluatorVersion": self.version,
            "normalizedResponse": normalized_response,
        }

    def _incorrect(
        self, question_type: str, *, normalized_response: Any
    ) -> dict[str, Any]:
        return self._scored(
            question_type, False, normalized_response=normalized_response
        )

    def _unsupported(
        self, reason: str, question_type: str = ""
    ) -> dict[str, Any]:
        return {
            "status": STATUS_UNSUPPORTED,
            "correct": None,
            "score": None,
            "questionType": question_type,
            "evaluatorVersion": self.version,
            "normalizedResponse": None,
            "reason": reason,
        }
