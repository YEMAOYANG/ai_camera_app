from __future__ import annotations

import json
import re
from typing import Any, Mapping, Protocol, Sequence

from integrations.openmaic_draft_adapter import (
    DraftGenerationResult,
    OPENMAIC_DRAFT_SCHEMA,
    OpenMaicDraftAdapter,
    OpenMaicDraftError,
)
from services.learning_question_evaluator import SCORED_DETERMINISTIC_TYPES


LEARNING_ENRICHMENT_SCHEMA = "mira.learning.enrichment.v1"

_ANSWER_AUTHORITY_KEYS = {
    "answer",
    "answers",
    "correct",
    "correctAnswer",
    "correctAnswers",
    "correct_answer",
    "correct_answers",
    "expectedAnswer",
    "expectedAnswers",
    "referenceAnswer",
    "referenceAnswers",
    "solution",
    "solutions",
    "analysis",
    "commentPrompt",
    "rubric",
    "gradingRubric",
    "hasAnswer",
    "isCorrect",
    "evaluation",
    "evaluationMode",
    "evaluator",
    "evaluatorVersion",
    "expected",
    "acceptedAnswers",
    "expectedOptionId",
    "expectedSequence",
    "passingScore",
    "score",
    "points",
}
_ACTION_OR_MEDIA_KEYS = {
    "action",
    "actions",
    "audio",
    "audios",
    "html",
    "image",
    "images",
    "media",
    "mediaGenerations",
    "mediaRef",
    "src",
    "video",
    "videos",
    "whiteboards",
}
_ALLOWED_SCENE_TYPES = {"slide", "quiz"}
_ALLOWED_DETERMINISTIC_SUBJECTS = {
    "chinese",
    "english",
    "math",
}
_ALLOWED_PRIMARY_GRADES = {f"primary_{grade}" for grade in range(1, 7)}
_REQUIRED_OUTCOME_MODE = "scored_deterministic"
_ANSWER_AUTHORITY_KEYS_NORMALIZED = {
    key.casefold() for key in _ANSWER_AUTHORITY_KEYS
}
_ACTION_OR_MEDIA_KEYS_NORMALIZED = {
    key.casefold() for key in _ACTION_OR_MEDIA_KEYS
}
_UNSAFE_RICH_TEXT = re.compile(
    r"<\s*/?\s*[a-z][^>]*>|&(?:lt|#0*60|#x0*3c);",
    re.IGNORECASE,
)


class LearningContentGenerationError(RuntimeError):
    """Stable business-layer error for unpublishable enrichment drafts."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class DraftAdapter(Protocol):
    def availability(self) -> dict[str, Any]: ...

    def generate(
        self, skill_boundary: Mapping[str, Any], request_id: str
    ) -> DraftGenerationResult: ...


class LearningContentGenerationService:
    """Adds unverified OpenMAIC teaching presentation to a deterministic course.

    A published Mira course is the authority for curriculum scope, questions,
    expected answers and verification expressions. This service exposes none of
    those answers to OpenMAIC. It only asks for an age-appropriate teaching
    outline, then validates the returned draft before another layer may attach
    it to a lesson experience.
    """

    def __init__(
        self,
        adapter: DraftAdapter | None = None,
        *,
        max_scenes: int = 4,
        max_text_chars: int = 30_000,
        max_single_text_chars: int = 4_000,
    ):
        self.adapter = adapter or OpenMaicDraftAdapter()
        self.max_scenes = max(1, min(int(max_scenes), 8))
        self.max_text_chars = max(1_000, int(max_text_chars))
        self.max_single_text_chars = max(200, int(max_single_text_chars))

    def status(self) -> dict[str, Any]:
        adapter_status = self.adapter.availability()
        return {
            "schemaVersion": LEARNING_ENRICHMENT_SCHEMA,
            "generator": "openmaic",
            "available": bool(adapter_status.get("available")),
            "adapter": adapter_status,
            "policy": {
                "sourceOfTruth": "published_deterministic_course",
                "answerSource": "mira_deterministic_validation_only",
                "allowedSceneTypes": sorted(_ALLOWED_SCENE_TYPES),
                "allowedSubjects": sorted(_ALLOWED_DETERMINISTIC_SUBJECTS),
                "requiredOutcomeMode": _REQUIRED_OUTCOME_MODE,
                "actionsEnabled": False,
                "mediaEnabled": False,
                "maxScenes": self.max_scenes,
            },
        }

    def generate(
        self,
        course: Mapping[str, Any],
        request_id: str,
        *,
        allowed_content: Sequence[str] | None = None,
        excluded_content: Sequence[str] | None = None,
        prerequisite_skills: Sequence[str] | None = None,
        duration_minutes: int | None = None,
    ) -> dict[str, Any]:
        source = self._normalize_published_course(course)
        boundary = self._build_skill_boundary(
            source,
            allowed_content=allowed_content,
            excluded_content=excluded_content,
            prerequisite_skills=prerequisite_skills,
            duration_minutes=duration_minutes,
        )
        try:
            generated = self.adapter.generate(boundary, request_id)
        except OpenMaicDraftError as exc:
            raise LearningContentGenerationError(
                self._adapter_error_code(exc.code), exc.message
            ) from exc
        except Exception as exc:
            raise LearningContentGenerationError(
                "openmaic_generation_failed", "OpenMAIC enrichment generation failed"
            ) from exc

        self._validate_generation(
            generated,
            source=source,
            boundary=boundary,
            request_id=str(request_id).strip(),
        )
        return {
            "schemaVersion": LEARNING_ENRICHMENT_SCHEMA,
            "requestId": generated.request_id,
            "status": "validated_draft",
            "generator": "openmaic",
            "provider": generated.provider,
            "model": generated.model,
            "elapsedMs": generated.elapsed_ms,
            "sourceCourse": {
                "id": source["id"],
                "version": source["version"],
                "gradeCode": source["gradeCode"],
                "subject": source["subject"],
                "skillId": source["nodeCode"],
            },
            "authority": {
                "curriculum": "published_deterministic_course",
                "questions": "published_deterministic_course",
                "answers": "mira_deterministic_validation_only",
                "openMaicRole": "presentation_and_interaction_draft_only",
                "authoritativeAnswersProvided": False,
            },
            "draft": generated.draft,
        }

    def _normalize_published_course(self, course: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(course, Mapping):
            self._reject("invalid_learning_course", "course must be an object")
        content = course.get("content")
        if content is None:
            content = course.get("content_json")
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError as exc:
                raise LearningContentGenerationError(
                    "invalid_learning_course", "published course content_json is invalid"
                ) from exc
        if not isinstance(content, Mapping):
            self._reject("invalid_learning_course", "published course content is required")

        source = {
            "id": self._text(course, "id", "id"),
            "version": self._text(course, "version", "version"),
            "gradeCode": self._text(course, "gradeCode", "grade_code"),
            "subject": self._text(course, "subject", "subject"),
            "nodeCode": self._text(course, "nodeCode", "node_code"),
            "title": self._text(course, "title", "title"),
            "objective": self._text(course, "objective", "objective"),
            "status": self._text(course, "status", "status"),
            "content": dict(content),
        }
        if source["status"] != "published":
            self._reject(
                "learning_course_not_published",
                "OpenMAIC enrichment requires a published deterministic course",
            )
        if source["gradeCode"] not in _ALLOWED_PRIMARY_GRADES:
            self._reject(
                "unsupported_learning_course",
                "only primary grades 1 through 6 are enabled for enrichment",
            )
        if source["subject"] not in _ALLOWED_DETERMINISTIC_SUBJECTS:
            self._reject(
                "unsupported_learning_course",
                "this subject is not enabled for deterministic OpenMAIC enrichment",
            )
        outcome_mode = str(
            source["content"].get("outcomeMode")
            or source["content"].get("evaluationMode")
            or source["content"].get("outcome_mode")
            or course.get("outcomeMode")
            or course.get("outcome_mode")
            or ""
        ).strip()
        if outcome_mode != _REQUIRED_OUTCOME_MODE:
            self._reject(
                "unsupported_learning_course",
                "OpenMAIC enrichment requires scored_deterministic content",
            )
        session_kind = str(
            source["content"].get("sessionKind")
            or source["content"].get("session_kind")
            or course.get("sessionKind")
            or course.get("session_kind")
            or ""
        ).strip()
        if session_kind != "lesson":
            self._reject(
                "unsupported_learning_course",
                "OpenMAIC enrichment requires lesson content",
            )
        questions = source["content"].get("questions")
        if not isinstance(questions, list) or not questions:
            self._reject(
                "invalid_learning_course",
                "published deterministic course must contain questions",
            )
        for question in questions:
            if not isinstance(question, Mapping):
                self._reject(
                    "invalid_learning_course",
                    "published deterministic course questions must be objects",
                )
            question_type = str(question.get("type") or "").strip()
            if question_type not in SCORED_DETERMINISTIC_TYPES:
                self._reject(
                    "unsupported_learning_course",
                    "OpenMAIC enrichment only accepts deterministic question types",
                )
            if not self._question_has_answer_authority(question, question_type):
                self._reject(
                    "invalid_learning_course",
                    "published deterministic course questions require authoritative answers",
                )
        source["outcomeMode"] = outcome_mode
        source["sessionKind"] = session_kind
        return source

    def _build_skill_boundary(
        self,
        source: dict[str, Any],
        *,
        allowed_content: Sequence[str] | None,
        excluded_content: Sequence[str] | None,
        prerequisite_skills: Sequence[str] | None,
        duration_minutes: int | None,
    ) -> dict[str, Any]:
        content = source["content"]
        questions = content["questions"]
        derived_allowed = [source["title"], source["objective"]]
        intro = str(content.get("intro") or "").strip()
        if intro:
            derived_allowed.append(intro)
        for question in questions:
            skill = str(question.get("skill") or "").strip()
            if skill:
                derived_allowed.append(skill)
        allowed = self._clean_list(allowed_content) if allowed_content is not None else self._clean_list(derived_allowed)
        excluded = self._clean_list(excluded_content)
        prerequisites = self._clean_list(prerequisite_skills)
        minutes = duration_minutes
        if minutes is None:
            minutes = int(content.get("estimatedMinutes") or 10)
        return {
            "gradeCode": source["gradeCode"],
            "subject": source["subject"],
            "skillId": source["nodeCode"],
            "skillTitle": source["title"],
            "learningObjectives": [source["objective"]],
            "allowedContent": allowed,
            "excludedContent": excluded,
            "prerequisiteSkills": prerequisites,
            "language": "zh-CN",
            "outcomeMode": source["outcomeMode"],
            "sessionKind": source["sessionKind"],
            "maxScenes": self.max_scenes,
            "durationMinutes": max(3, min(int(minutes), 45)),
        }

    def _validate_generation(
        self,
        generated: DraftGenerationResult,
        *,
        source: dict[str, Any],
        boundary: dict[str, Any],
        request_id: str,
    ) -> None:
        if (
            generated.schema_version != OPENMAIC_DRAFT_SCHEMA
            or generated.generator != "openmaic"
            or generated.request_id != request_id
        ):
            self._reject("invalid_openmaic_draft", "OpenMAIC result identity is invalid")
        draft = generated.draft
        if draft.get("status") != "unverified":
            self._reject("invalid_openmaic_draft", "OpenMAIC source draft must be unverified")
        if draft.get("authoritativeAnswersProvided") is not False:
            self._reject("invalid_openmaic_draft", "OpenMAIC must not provide answer authority")
        returned_boundary = draft.get("skillBoundary")
        if not isinstance(returned_boundary, Mapping):
            self._reject("invalid_openmaic_draft", "OpenMAIC draft lost its skill boundary")
        expected_identity = {
            "gradeCode": source["gradeCode"],
            "subject": source["subject"],
            "skillId": source["nodeCode"],
        }
        for key, expected in boundary.items():
            if returned_boundary.get(key) != expected:
                self._reject(
                    "openmaic_boundary_mismatch",
                    f"OpenMAIC draft changed fixed {key}",
                )
        for key, expected in expected_identity.items():
            if boundary.get(key) != expected:
                self._reject(
                    "openmaic_boundary_mismatch",
                    f"OpenMAIC request changed fixed {key}",
                )

        scenes = draft.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            self._reject("invalid_openmaic_draft", "OpenMAIC draft has no teaching scenes")
        if len(scenes) > self.max_scenes:
            self._reject("openmaic_limit_exceeded", "OpenMAIC draft contains too many scenes")
        total_text_chars = self._validate_draft_tree(draft, path="draft")
        for scene in scenes:
            if not isinstance(scene, Mapping):
                self._reject("invalid_openmaic_draft", "OpenMAIC scene must be an object")
            if scene.get("type") not in _ALLOWED_SCENE_TYPES:
                self._reject(
                    "openmaic_unsafe_scene",
                    "OpenMAIC interactive/PBL scenes are disabled for primary learning",
                )
        if total_text_chars > self.max_text_chars:
            self._reject("openmaic_limit_exceeded", "OpenMAIC draft text is too long")

    def _validate_draft_tree(self, value: Any, *, path: str = "scene") -> int:
        if isinstance(value, str):
            if len(value) > self.max_single_text_chars:
                self._reject("openmaic_limit_exceeded", f"OpenMAIC text is too long at {path}")
            if _UNSAFE_RICH_TEXT.search(value):
                self._reject(
                    "openmaic_unsafe_scene",
                    f"OpenMAIC draft contains unsafe rich text at {path}",
                )
            return len(value)
        if isinstance(value, list):
            return sum(
                self._validate_draft_tree(item, path=f"{path}[{index}]")
                for index, item in enumerate(value)
            )
        if not isinstance(value, Mapping):
            return 0
        total = 0
        for key, child in value.items():
            normalized_key = str(key).casefold()
            if normalized_key in _ANSWER_AUTHORITY_KEYS_NORMALIZED:
                self._reject(
                    "openmaic_answer_authority_leak",
                    f"OpenMAIC draft contains forbidden answer field: {key}",
                )
            if normalized_key in _ACTION_OR_MEDIA_KEYS_NORMALIZED:
                self._reject(
                    "openmaic_unsafe_scene",
                    f"OpenMAIC draft contains disabled action/media field: {key}",
                )
            if key == "elements" and isinstance(child, list):
                for element in child:
                    if isinstance(element, Mapping) and element.get("type") in {"image", "video"}:
                        self._reject(
                            "openmaic_unsafe_scene",
                            "OpenMAIC image/video elements are disabled",
                        )
            total += self._validate_draft_tree(child, path=f"{path}.{key}")
        return total

    @staticmethod
    def _question_has_answer_authority(
        question: Mapping[str, Any], question_type: str
    ) -> bool:
        evaluation = question.get("evaluation")
        if evaluation is None:
            evaluation = {}
        if not isinstance(evaluation, Mapping):
            return False
        if question_type == "accepted_text":
            value = evaluation.get(
                "acceptedAnswers", question.get("acceptedAnswers")
            )
            if value is None and isinstance(question.get("answer"), list):
                value = question.get("answer")
            return isinstance(value, list) and bool(value)
        if question_type == "sequence":
            value = evaluation.get(
                "expectedSequence",
                evaluation.get("expected", question.get("answer")),
            )
            return isinstance(value, list) and bool(value)
        if question_type == "single_choice":
            value = evaluation.get(
                "expectedOptionId",
                evaluation.get("expected", question.get("answer")),
            )
        else:
            value = evaluation.get(
                "expected",
                evaluation.get("expectedAnswer", question.get("answer")),
            )
        return (
            value is not None
            and not isinstance(value, (bool, Mapping, list, tuple, set))
            and bool(str(value).strip())
        )

    @staticmethod
    def _adapter_error_code(code: str) -> str:
        if code == "openmaic_unavailable":
            return "openmaic_unavailable"
        if code == "openmaic_timeout":
            return "openmaic_timeout"
        if code == "invalid_input":
            return "invalid_openmaic_request"
        return "openmaic_generation_failed"

    @staticmethod
    def _clean_list(values: Sequence[str] | None) -> list[str]:
        if values is None:
            return []
        cleaned: list[str] = []
        for value in values:
            text = str(value).strip()
            if text and text not in cleaned:
                cleaned.append(text)
        return cleaned

    @staticmethod
    def _text(course: Mapping[str, Any], camel: str, snake: str) -> str:
        value = course.get(camel)
        if value is None:
            value = course.get(snake)
        text = str(value or "").strip()
        if not text:
            raise LearningContentGenerationError(
                "invalid_learning_course", f"published course is missing {camel}"
            )
        return text

    @staticmethod
    def _reject(code: str, message: str):
        raise LearningContentGenerationError(code, message)
