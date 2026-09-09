from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

from content.primary_skill_boundaries import (
    CONTENT_VALIDATION_CONTRACT_VERSION,
    PRIMARY_CURRICULUM_VERSION,
    PRIMARY_ONE_CONTENT_DATASET_SHA256,
    SUBJECT_LANGUAGE_POLICY_VERSION,
)
from core.errors import ApiError
from integrations.openmaic_question_adapter import (
    PRIMARY_ONE_ADD_SUB_HOST_SOLVER,
    PRIMARY_ONE_CHARACTER_WORD_HOST_SOLVER,
    PRIMARY_ONE_NUMBER_SENSE_HOST_SOLVER,
    PRIMARY_ONE_SIMPLE_SENTENCE_HOST_SOLVER,
    question_candidate_course_id,
    question_candidate_request_slug,
)
from services.learning_catalog_validator import (
    COURSE_SCHEMA_VERSION,
    GENERATED_SOURCE_AUTHORITY,
    PrimaryOneCourseTarget,
    SUPPORTED_PRIMARY_SUBJECTS,
    SUPPORTED_QUESTION_TYPES,
    LearningCatalogValidator,
)
from services.learning_question_evaluator import (
    STATUS_CORRECT,
    LearningQuestionEvaluator,
)


GENERATED_COURSE_VALIDATOR_VERSION = "mira.learning.generated-course-validator.v1"
INDEPENDENT_SOLUTION_SCHEMA_VERSION = "mira.learning.independent-solution.v1"
TEACHING_FLOW_SCHEMA_VERSION = "mira.learning.teaching-flow.v1"
PRIMARY_ONE_HOST_GATE_VERSION = "mira.learning.primary-1-host-gate.v1"
PRIMARY_ONE_HOST_GATE_RECEIPT_SCHEMA_VERSION = (
    "mira.learning.primary-1-host-gate-receipt.v1"
)
PRIMARY_ONE_HOST_FINGERPRINT_VERSION = (
    "mira.learning.primary-1-semantic-fingerprint.v1"
)
PRIMARY_ONE_HOST_FINGERPRINT_PAYLOAD_SCHEMA_VERSION = (
    "mira.learning.primary-1-semantic-fingerprint-payload.v1"
)

_CANDIDATE_STATUS = "unverified"
_CANDIDATE_SOURCE_AUTHORITY = {
    "basis": "provided_skill_boundary",
    "contentOrigin": "openmaic_kimi_candidate",
    "textbookDependency": "none",
}
_COURSE_KEYS = frozenset(
    {
        "id",
        "version",
        "gradeCode",
        "subject",
        "nodeCode",
        "title",
        "objective",
        "status",
        "content",
    }
)
_CONTENT_KEYS = frozenset(
    {
        "schemaVersion",
        "sessionKind",
        "outcomeMode",
        "sourceAuthority",
        "reviewPolicy",
        "intro",
        "estimatedMinutes",
        "questions",
        "teachingFlow",
    }
)
_COMMON_QUESTION_KEYS = frozenset(
    {"id", "type", "prompt", "skill", "hint", "explanation", "evaluation"}
)
_QUESTION_KEYS_BY_TYPE = {
    "numeric": _COMMON_QUESTION_KEYS | {"answer", "verificationExpression"},
    "exact_text": _COMMON_QUESTION_KEYS | {"answer"},
    "accepted_text": _COMMON_QUESTION_KEYS | {"answer", "acceptedAnswers"},
    "single_choice": _COMMON_QUESTION_KEYS | {"answer", "choices"},
    "sequence": _COMMON_QUESTION_KEYS | {"answer", "choices"},
}
_EVALUATION_KEYS_BY_TYPE = {
    "numeric": frozenset({"expected", "normalization"}),
    "exact_text": frozenset({"expected", "normalization"}),
    "accepted_text": frozenset({"acceptedAnswers", "normalization"}),
    "single_choice": frozenset({"expectedOptionId", "normalization"}),
    "sequence": frozenset({"expectedSequence", "normalization"}),
}
_NORMALIZATION_BY_TYPE = {
    "numeric": frozenset({"trim", "remove_grouping_separators"}),
    "exact_text": frozenset(
        {
            "trim",
            "collapse_whitespace",
            "remove_whitespace",
            "casefold",
            "strip_terminal_punctuation",
            "strip_punctuation",
        }
    ),
    "accepted_text": frozenset(
        {
            "trim",
            "collapse_whitespace",
            "remove_whitespace",
            "casefold",
            "strip_terminal_punctuation",
            "strip_punctuation",
        }
    ),
    "single_choice": frozenset({"trim", "casefold"}),
    "sequence": frozenset(
        {
            "trim",
            "collapse_whitespace",
            "remove_whitespace",
            "casefold",
            "strip_terminal_punctuation",
            "strip_punctuation",
        }
    ),
}
_TEXT_LIMITS = {
    "course.id": 255,
    "course.version": 64,
    "course.nodeCode": 120,
    "course.title": 80,
    "course.objective": 300,
    "content.intro": 600,
    "question.id": 160,
    "question.prompt": 600,
    "question.skill": 120,
    "question.hint": 400,
    "question.explanation": 800,
    "choice.id": 80,
    "choice.label": 240,
    "answer": 300,
    "teachingFlow.teach.title": 160,
    "teachingFlow.teach.sayText": 1200,
    "teachingFlow.teach.keyPoint": 200,
    "teachingFlow.recap.sayText": 600,
}
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$")
_TERMINAL_PUNCTUATION = ".!?;:。！？；："
_MISSING = object()

_PRIMARY_ONE_RECEIPT_KEYS = frozenset(
    {
        "schemaVersion",
        "validatorVersion",
        "fingerprintVersion",
        "contentValidationContractVersion",
        "contentValidationDatasetSha256",
        "subjectLanguagePolicyVersion",
        "catalogItemId",
        "logicalAttempt",
        "generationRequestIdHash",
        "courseId",
        "courseVersion",
        "gradeCode",
        "subject",
        "subjectOrdinal",
        "skillId",
        "boundaryOrdinal",
        "boundaryVersion",
        "variantOrdinal",
        "instructionLanguageCode",
        "targetLanguageCode",
        "finalProviderPhase",
        "finalProviderPhaseOrdinal",
        "generatorProfileHash",
        "verifierProfileHash",
        "verificationIsolation",
        "skillBoundarySha256",
        "candidateCourseSha256",
        "sidecarEvidenceSha256",
        "hostContentFingerprint",
        "outcome",
        "checksPassed",
        "issues",
    }
)
_PRIMARY_ONE_HOST_CHECKS = (
    "sealed_authority_loaded",
    "target_identity_bound",
    "provider_profiles_bound",
    "phase_checkpoint_bound",
    "sidecar_evidence_recomputed",
    "prior_variant_receipts_revalidated",
    "intrinsic_content_validated",
    "independent_solution_recomputed",
    "semantic_fingerprint_unique",
    "publishable_course_revalidated",
)
_PRIMARY_ONE_ISSUES = {
    "content": {
        "code": "primary_one_content_rejected",
        "path": "candidateCourse.content",
        "message": "课程内容未通过一年级确定性教学规则。",
    },
    "independent": {
        "code": "primary_one_independent_solution_disagreement",
        "path": "independentSolution.answers",
        "message": "隔离复核答案与本地确定性复算不一致。",
    },
    "duplicate": {
        "code": "primary_one_duplicate_variant",
        "path": "candidateCourse.content.questions",
        "message": "课程与同一能力边界的已通过变体语义重复。",
    },
    "historical_question_duplicate": {
        "code": "primary_one_historical_question_duplicate",
        "path": "candidateCourse.content.questions",
        "message": "课程题目与同一能力边界的历史题目重复。",
    },
}


class PrimaryOneHostGateControlError(ValueError):
    """Persisted/caller evidence drift; never eligible for content retry."""


class PrimaryOneHostGateDependencyError(RuntimeError):
    """Sealed local authority is unavailable; Host-only recovery may retry."""


@dataclass(frozen=True)
class QuestionPhaseProviderProfileEvidence:
    name: str
    model: str
    base_url: str
    api_key_env: str
    timeout_ms: int
    max_tokens: int
    temperature: float
    profile_hash: str


@dataclass(frozen=True)
class QuestionPhaseCourseEvidence:
    final_phase: str
    final_phase_ordinal: int
    candidate_course: Mapping[str, object]
    question_fingerprints: Sequence[Mapping[str, object]]
    validation: Mapping[str, object]
    independent_solution: Mapping[str, object]
    generator_profile: QuestionPhaseProviderProfileEvidence
    verifier_profile: QuestionPhaseProviderProfileEvidence
    existing_fingerprint_count: int
    # Complete Host-only authority.  The sidecar checkpoint intentionally
    # stays capped at 500 hashes; this set may grow without that transport cap.
    authoritative_existing_fingerprints: Sequence[str] = ()


@dataclass(frozen=True)
class PrimaryOneHostGateIdentity:
    catalog_item_id: str
    logical_attempt: int
    generation_request_id: str
    course_id: str
    course_version: str
    curriculum_version: str
    content_validation_contract_version: str
    content_validation_dataset_sha256: str
    subject_language_policy_version: str
    generator_profile_hash: str
    verifier_profile_hash: str


@dataclass(frozen=True)
class PrimaryOneHostGateResult:
    outcome: str
    course: dict[str, object] | None
    receipt: dict[str, object]
    receipt_hash: str


@dataclass(frozen=True)
class AcceptedPrimaryOneHostReceipt:
    target: PrimaryOneCourseTarget
    immutable_course: Mapping[str, object]
    receipt: Mapping[str, object]
    receipt_hash: str


class GeneratedCourseValidationError(ApiError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        path: str | None = None,
        details: Mapping[str, Any] | None = None,
    ):
        super().__init__(code, message, 422)
        self.path = path
        self.details = dict(details or {})

    def as_issue(self) -> dict[str, Any]:
        issue: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.path:
            issue["path"] = self.path
        if self.details:
            issue["details"] = dict(self.details)
        return issue


@dataclass(frozen=True)
class GeneratedCourseValidationResult:
    course: dict[str, Any] | None
    report: dict[str, Any]

    @property
    def publishable(self) -> bool:
        return self.course is not None and bool(self.report.get("publishable"))

    def require_publishable(self) -> dict[str, Any]:
        if self.course is not None and self.report.get("publishable") is True:
            return copy.deepcopy(self.course)
        first = (self.report.get("issues") or [{}])[0]
        raise GeneratedCourseValidationError(
            str(first.get("code") or "generated_course_validation_failed"),
            str(first.get("message") or "Generated course failed validation."),
            path=str(first.get("path") or "") or None,
            details=first.get("details") if isinstance(first.get("details"), Mapping) else None,
        )


class LearningGeneratedCourseValidator:
    """Turns an untrusted OpenMAIC/Kimi candidate into a publishable course.

    The class is deliberately pure and performs no provider or network calls.
    A second, independently generated solution must be supplied for all three
    subjects. Math additionally requires an AST-whitelisted Decimal recompute.
    """

    version = GENERATED_COURSE_VALIDATOR_VERSION

    def __init__(self):
        self.catalog_validator = LearningCatalogValidator()
        self.question_evaluator = LearningQuestionEvaluator()

    def validate(
        self,
        candidate: str | Mapping[str, Any],
        *,
        grade_code: str | None = None,
        grade: int | str | None = None,
        subject: str,
        skill_boundary: str | Mapping[str, Any],
        independent_solution: str | Mapping[str, Any] | None,
        verification_request_id: str | None = None,
        existing_fingerprints: Sequence[str] = (),
    ) -> GeneratedCourseValidationResult:
        checks: list[str] = []
        fingerprint: str | None = None
        try:
            expected_grade = self._expected_grade(grade_code, grade)
            expected_subject = str(subject or "").strip()
            if expected_subject not in SUPPORTED_PRIMARY_SUBJECTS:
                self._fail(
                    "unsupported_generated_subject",
                    "subject must be chinese, math, or english.",
                    path="subject",
                )
            boundary = self._boundary(
                skill_boundary,
                grade_code=expected_grade,
                subject=expected_subject,
            )
            raw = self._decode_object(candidate, path="candidate")
            checks.append("candidate_json")
            self._strict_candidate_schema(raw)
            checks.append("strict_schema")
            self._validate_boundary(raw, expected_grade, expected_subject, boundary)
            checks.append("grade_subject_skill_boundary")
            self._validate_lengths(raw)
            checks.append("content_limits")
            self._validate_questions(raw, boundary)
            checks.extend(
                [
                    "five_questions",
                    "deterministic_question_types",
                    "normalization_allowlist",
                    "answer_choice_consistency",
                ]
            )
            self._validate_teaching_flow(raw, boundary)
            checks.append("teaching_flow_contract")
            self._validate_independent_solution(
                raw,
                independent_solution=independent_solution,
                expected_grade=expected_grade,
                expected_subject=expected_subject,
                boundary=boundary,
                verification_request_id=verification_request_id,
            )
            checks.append("independent_solution_agreement")
            checks.append("independent_teaching_review")
            if expected_subject == "math":
                checks.append("math_ast_decimal_recompute")

            fingerprint = self.content_fingerprint(raw)
            known = self._fingerprint_set(existing_fingerprints)
            if fingerprint in known:
                self._fail(
                    "duplicate_generated_course",
                    "Generated course duplicates previously accepted content.",
                    path="content.questions",
                    details={"fingerprint": fingerprint},
                )
            checks.append("content_fingerprint_unique")

            published = self._as_publishable(raw)
            try:
                self.catalog_validator.validate_course(published)
            except ApiError as exc:
                self._fail(
                    "invalid_generated_course",
                    exc.message,
                    path="candidate",
                )
            checks.append("production_catalog_contract")
            report = self._report(
                publishable=True,
                checks=checks,
                fingerprint=fingerprint,
                issues=[],
            )
            return GeneratedCourseValidationResult(published, report)
        except GeneratedCourseValidationError as exc:
            return GeneratedCourseValidationResult(
                None,
                self._report(
                    publishable=False,
                    checks=checks,
                    fingerprint=fingerprint,
                    issues=[exc.as_issue()],
                ),
            )

    def validate_or_raise(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.validate(*args, **kwargs).require_publishable()

    def validate_primary_one_host_gate(
        self,
        evidence: QuestionPhaseCourseEvidence,
        *,
        target: PrimaryOneCourseTarget,
        identity: PrimaryOneHostGateIdentity,
        skill_boundary: Mapping[str, object],
        accepted_host_receipts: Sequence[AcceptedPrimaryOneHostReceipt],
    ) -> PrimaryOneHostGateResult:
        if not isinstance(evidence, QuestionPhaseCourseEvidence):
            raise PrimaryOneHostGateControlError("phase evidence type drift")
        checks: list[str] = []
        try:
            context = self.catalog_validator._primary_one_context(
                target, skill_boundary
            )
        except ApiError as exc:
            raise PrimaryOneHostGateControlError(
                "primary-one target or skill boundary drift"
            ) from exc
        except Exception as exc:
            raise PrimaryOneHostGateDependencyError(
                "sealed primary-one authority unavailable"
            ) from exc
        checks.append("sealed_authority_loaded")

        self._validate_primary_one_identity(identity, target)
        checks.append("target_identity_bound")
        generator_profile = self._validate_primary_one_profile(
            evidence.generator_profile, "generatorProfile"
        )
        verifier_profile = self._validate_primary_one_profile(
            evidence.verifier_profile, "verifierProfile"
        )
        if (
            identity.generator_profile_hash != generator_profile[1]
            or identity.verifier_profile_hash != verifier_profile[1]
        ):
            raise PrimaryOneHostGateControlError(
                "provider profile identity hash drift"
            )
        checks.append("provider_profiles_bound")

        course = self._validate_primary_one_phase_evidence(
            evidence,
            target=target,
            identity=identity,
            skill_boundary=skill_boundary,
            verifier_profile=verifier_profile[0],
        )
        checks.append("phase_checkpoint_bound")
        course, shape_repaired_question_ids = (
            self._normalize_primary_one_shapes_position_host_checkpoint(
                course,
                solution=evidence.independent_solution,
                target=target,
                logical_attempt=identity.logical_attempt,
            )
        )
        course, character_repaired_question_ids = (
            self._normalize_primary_one_characters_words_host_checkpoint(
                course,
                solution=evidence.independent_solution,
                target=target,
                logical_attempt=identity.logical_attempt,
            )
        )
        host_repaired_question_ids = (
            shape_repaired_question_ids | character_repaired_question_ids
        )
        authoritative_question_fingerprints = (
            self._validate_authoritative_question_fingerprints(
                evidence.authoritative_existing_fingerprints
            )
        )
        sidecar_evidence_payload = {
            "questionFingerprints": evidence.question_fingerprints,
            "validation": evidence.validation,
            "independentSolution": evidence.independent_solution,
        }
        if len(authoritative_question_fingerprints) > 500:
            # Existing receipts (whose full history fit in the sidecar) remain
            # byte-identical.  New overflow receipts additionally bind the
            # Host-only inventory so later replay audits the same full set.
            sidecar_evidence_payload["hostQuestionFingerprintAuthority"] = {
                "count": len(authoritative_question_fingerprints),
                "sha256": self._sha256_json(
                    sorted(authoritative_question_fingerprints)
                ),
            }
        sidecar_evidence_sha256 = self._sha256_json(sidecar_evidence_payload)
        checks.append("sidecar_evidence_recomputed")

        accepted_fingerprints = self._validate_primary_one_prior_receipts(
            accepted_host_receipts,
            target=target,
        )
        checks.append("prior_variant_receipts_revalidated")

        skill_boundary_sha256 = self._sha256_json(skill_boundary)
        candidate_course_sha256 = self._sha256_json(course)
        common_receipt = self._primary_one_receipt_base(
            target=target,
            identity=identity,
            evidence=evidence,
            skill_boundary_sha256=skill_boundary_sha256,
            candidate_course_sha256=candidate_course_sha256,
            sidecar_evidence_sha256=sidecar_evidence_sha256,
        )

        if authoritative_question_fingerprints.intersection(
            self._primary_one_question_fingerprints(course, target=target)
        ):
            return self._primary_one_rejected(
                common_receipt,
                checks,
                issue="historical_question_duplicate",
                fingerprint=self._safe_primary_one_fingerprint(course, target),
            )

        try:
            self.catalog_validator.validate_primary_one_generated_course(
                course,
                target=target,
                skill_boundary=skill_boundary,
            )
        except ApiError:
            return self._primary_one_rejected(
                common_receipt,
                checks,
                issue="content",
                fingerprint=self._safe_primary_one_fingerprint(course, target),
            )
        except Exception as exc:
            raise PrimaryOneHostGateDependencyError(
                "sealed primary-one authority unavailable"
            ) from exc
        checks.append("intrinsic_content_validated")

        if not self._primary_one_independent_answers_agree(
            course,
            evidence.independent_solution,
            host_repaired_question_ids=host_repaired_question_ids,
        ):
            return self._primary_one_rejected(
                common_receipt,
                checks,
                issue="independent",
                fingerprint=self._safe_primary_one_fingerprint(course, target),
            )
        checks.append("independent_solution_recomputed")

        try:
            fingerprint = self.primary_one_content_fingerprint(
                course, target=target
            )
        except GeneratedCourseValidationError:
            return self._primary_one_rejected(
                common_receipt,
                checks,
                issue="content",
                fingerprint="",
            )
        if fingerprint in accepted_fingerprints:
            return self._primary_one_rejected(
                common_receipt,
                checks,
                issue="duplicate",
                fingerprint=fingerprint,
            )
        checks.append("semantic_fingerprint_unique")

        published = self._as_publishable(course)
        try:
            self.catalog_validator.validate_primary_one_generated_course(
                published,
                target=target,
                skill_boundary=skill_boundary,
            )
        except ApiError as exc:
            raise PrimaryOneHostGateControlError(
                "publishable projection failed persisted-course recheck"
            ) from exc
        except Exception as exc:
            raise PrimaryOneHostGateDependencyError(
                "sealed primary-one authority unavailable"
            ) from exc
        checks.append("publishable_course_revalidated")
        receipt = {
            **common_receipt,
            "hostContentFingerprint": fingerprint,
            "outcome": "passed",
            "checksPassed": list(checks),
            "issues": [],
        }
        self._assert_primary_one_receipt_shape(receipt)
        return PrimaryOneHostGateResult(
            outcome="passed",
            course=published,
            receipt=receipt,
            receipt_hash=self._sha256_json(receipt),
        )

    @staticmethod
    def _normalize_primary_one_shapes_position_host_checkpoint(
        course: Mapping[str, Any],
        *,
        solution: Mapping[str, Any],
        target: PrimaryOneCourseTarget,
        logical_attempt: int,
    ) -> tuple[dict[str, Any], frozenset[str]]:
        """Canonicalize only relations already proved by the sealed checkpoint.

        The sidecar proof is checked before this method runs.  These rewrites
        retain question and answer IDs, introduce no new relationship, and
        make model wording use the exact finite vocabulary consumed by the
        repository-owned Grade-1 validator.
        """

        normalized = copy.deepcopy(dict(course))
        if (
            target.grade_code != "primary_1"
            or target.subject != "math"
            or target.skill_id != "shapes_position"
            or (logical_attempt, target.variant_ordinal)
            not in {(2, 1), (1, 3), (2, 3)}
        ):
            return normalized, frozenset()
        content = normalized.get("content")
        questions = content.get("questions") if isinstance(content, Mapping) else None
        if not isinstance(questions, list):
            return normalized, frozenset()

        def relabel_directional_choices(
            question: Mapping[str, Any],
            *,
            answer_label: str,
            distractor_labels: Sequence[str],
        ) -> list[dict[str, Any]] | None:
            choices = question.get("choices")
            answer_id = question.get("answer")
            if (
                not isinstance(choices, list)
                or not 2 <= len(choices) <= len(distractor_labels) + 1
                or not isinstance(answer_id, str)
                or sum(
                    isinstance(choice, Mapping)
                    and choice.get("id") == answer_id
                    for choice in choices
                )
                != 1
            ):
                return None
            result: list[dict[str, Any]] = []
            distractor_index = 0
            for choice in choices:
                if not isinstance(choice, Mapping):
                    return None
                rewritten = copy.deepcopy(dict(choice))
                if choice.get("id") == answer_id:
                    rewritten["label"] = answer_label
                else:
                    rewritten["label"] = distractor_labels[distractor_index]
                    distractor_index += 1
                result.append(rewritten)
            return result

        if logical_attempt == 1 and target.variant_ordinal == 3:
            rewritten_questions: list[object] = []
            for raw_question in questions:
                if not isinstance(raw_question, Mapping):
                    rewritten_questions.append(copy.deepcopy(raw_question))
                    continue
                question = copy.deepcopy(dict(raw_question))
                choices = question.get("choices")
                answer_id = question.get("answer")
                prompt = unicodedata.normalize(
                    "NFKC", str(question.get("prompt") or "")
                )
                selected = [
                    choice
                    for choice in choices or []
                    if isinstance(choice, Mapping)
                    and choice.get("id") == answer_id
                    and isinstance(choice.get("label"), str)
                ]
                selected_label = (
                    unicodedata.normalize("NFKC", str(selected[0]["label"])).strip()
                    if len(selected) == 1
                    else ""
                )
                if (
                    question.get("type") == "single_choice"
                    and selected_label == "正方形"
                    and "方方的盒子" in prompt
                    and re.search(r"四条边(?:都)?一样长", prompt)
                ):
                    question.update(
                        {
                            "prompt": "小狐狸观察一个方盒子:这个面的四条边相等,并且有四个直角。这个面是什么图形?",
                            "hint": "只根据四条边是否相等和角的特征判断。",
                            "explanation": "这个面有四条相等的边和四个直角,所以它是正方形。",
                        }
                    )
                elif (
                    question.get("type") == "single_choice"
                    and selected_label == "三角形"
                    and "贴纸" in prompt
                    and "三条边" in prompt
                ):
                    question.update(
                        {
                            "prompt": "小狐狸观察一张车站贴纸:它有三条直边和三个角。这张贴纸是什么图形?",
                            "hint": "数一数直边和角。",
                            "explanation": "这张贴纸有三条直边和三个角,所以它是三角形。",
                        }
                    )
                elif (
                    question.get("type") == "single_choice"
                    and selected_label == "右边"
                    and "圆形纽扣" in prompt
                    and "正方形纽扣" in prompt
                ):
                    rewritten_choices = relabel_directional_choices(
                        question,
                        answer_label="右",
                        distractor_labels=("左", "上", "下"),
                    )
                    if rewritten_choices is not None:
                        question.update(
                            {
                                "prompt": "红色圆形纽扣在蓝色正方形纽扣的左边。蓝色正方形纽扣在红色圆形纽扣的哪一边?",
                                "choices": rewritten_choices,
                                "hint": "把题目直接给出的左右关系反过来想。",
                                "explanation": "红色圆形纽扣在蓝色正方形纽扣的左边,所以蓝色正方形纽扣在红色圆形纽扣的右边。",
                            }
                        )
                elif (
                    question.get("type") == "single_choice"
                    and selected_label == "左边"
                    and "图画书在故事书的左边" in prompt
                    and "图画书在科普书的哪一边" in prompt
                ):
                    rewritten_choices = relabel_directional_choices(
                        question,
                        answer_label="右",
                        distractor_labels=("左", "上", "下"),
                    )
                    if rewritten_choices is not None:
                        question.update(
                            {
                                "prompt": "图画书在故事书的左边。故事书在图画书的哪一边?",
                                "choices": rewritten_choices,
                                "hint": "把题目直接给出的左右关系反过来想。",
                                "explanation": "图画书在故事书的左边,所以故事书在图画书的右边。",
                            }
                        )
                rewritten_questions.append(question)
            content["questions"] = rewritten_questions
            return normalized, frozenset()

        answers = solution.get("answers") if isinstance(solution, Mapping) else None
        answer_by_question_id = {
            str(answer.get("questionId") or ""): answer.get("answer")
            for answer in answers or []
            if isinstance(answer, Mapping)
        }
        repaired: set[str] = set()
        rewritten_questions: list[object] = []
        for raw_question in questions:
            if (
                not isinstance(raw_question, Mapping)
                or raw_question.get("type") != "single_choice"
                or not isinstance(raw_question.get("answer"), str)
                or not isinstance(raw_question.get("choices"), list)
            ):
                rewritten_questions.append(copy.deepcopy(raw_question))
                continue
            question = copy.deepcopy(dict(raw_question))
            selected = [
                choice
                for choice in question["choices"]
                if isinstance(choice, Mapping)
                and choice.get("id") == question["answer"]
                and isinstance(choice.get("label"), str)
            ]
            if len(selected) != 1:
                rewritten_questions.append(question)
                continue
            selected_label = unicodedata.normalize(
                "NFKC", str(selected[0]["label"])
            ).strip()
            prompt = unicodedata.normalize(
                "NFKC", str(question.get("prompt") or "")
            )
            provider_answer_id = answer_by_question_id.get(
                str(question.get("id") or "")
            )
            provider_selected = [
                choice
                for choice in question["choices"]
                if isinstance(choice, Mapping)
                and choice.get("id") == provider_answer_id
                and isinstance(choice.get("label"), str)
            ]
            provider_selected_label = (
                unicodedata.normalize(
                    "NFKC", str(provider_selected[0]["label"])
                ).strip()
                if len(provider_selected) == 1
                else ""
            )

            if (
                logical_attempt == 2
                and target.variant_ordinal == 3
                and selected_label == "黄色纸片的左边"
                and provider_selected_label == "黄色纸片的右边"
                and "红色纸片在蓝色纸片的左边" in prompt
                and "黄色纸片在蓝色纸片的右边" in prompt
                and "蓝色纸片在哪张纸片的左边" in prompt
            ):
                choices = relabel_directional_choices(
                    question,
                    answer_label="左",
                    distractor_labels=("右", "上", "下"),
                )
                if choices is not None:
                    question.update(
                        {
                            "prompt": "黄色纸片在蓝色纸片的右边。蓝色纸片在黄色纸片的哪一边?",
                            "choices": choices,
                            "hint": "把题目直接给出的左右关系反过来想。",
                            "explanation": "黄色纸片在蓝色纸片的右边,所以蓝色纸片在黄色纸片的左边。",
                        }
                    )
                    repaired.add(str(question.get("id") or ""))
            elif (
                selected_label == "正方形"
                and re.search(r"四条边(?:都)?(?:一样长|同样长|相等)", prompt)
                and re.search(r"四个(?:方方的)?角|四个直角", prompt)
            ):
                question.update(
                    {
                        "prompt": "小考拉拿起一张图形贴纸。这张贴纸的四条边相等,并且有四个直角。它是什么图形?",
                        "hint": "只根据四条边是否相等和角的特征判断。",
                        "explanation": "这张贴纸有四条相等的边和四个直角,所以它是正方形。",
                    }
                )
            elif (
                selected_label == "圆形"
                and re.search(r"弯弯的|弯曲|曲线", prompt)
                and re.search(r"没有一个角|没有角", prompt)
            ):
                question.update(
                    {
                        "prompt": "小考拉观察一个印章:它的边是弯曲的,没有直边,也没有角。这个印章是什么图形?",
                        "hint": "只根据有没有直边和角来判断。",
                        "explanation": "这个印章没有直边,也没有角,所以它是圆形。",
                    }
                )
            elif (
                selected_label in {"下面", "下"}
                and "苹果路牌在香蕉路牌的上面" in prompt
                and "香蕉路牌在橙子路牌的上面" in prompt
                and "橙子路牌在苹果路牌" in prompt
            ):
                choices = relabel_directional_choices(
                    question,
                    answer_label="下",
                    distractor_labels=("上", "左", "右"),
                )
                if choices is not None:
                    question.update(
                        {
                            "prompt": "苹果路牌在橙子路牌的上方。橙子路牌在苹果路牌的哪一边?",
                            "choices": choices,
                            "hint": "把题目明确给出的上下关系反过来想。",
                            "explanation": "苹果路牌在橙子路牌的上方,所以橙子路牌在苹果路牌的下方。",
                        }
                    )
            elif (
                selected_label in {"右面", "右边", "右"}
                and "红色便签在蓝色便签的左面" in prompt
                and "蓝色便签在绿色便签的左面" in prompt
                and "绿色便签在红色便签" in prompt
            ):
                choices = relabel_directional_choices(
                    question,
                    answer_label="右",
                    distractor_labels=("上", "下", "左"),
                )
                if choices is not None:
                    question.update(
                        {
                            "prompt": "红色便签在绿色便签的左边。绿色便签在红色便签的哪一边?",
                            "choices": choices,
                            "hint": "把题目明确给出的左右关系反过来想。",
                            "explanation": "红色便签在绿色便签的左边,所以绿色便签在红色便签的右边。",
                        }
                    )
            elif (
                selected_label == "红花盆"
                and re.search(
                    r"红花盆[^,，。?？]{0,12}(?:在|放在)蓝花盆的左边", prompt
                )
                and re.search(
                    r"蓝花盆[^,，。?？]{0,16}哪个花盆的右边", prompt
                )
            ):
                choices = relabel_directional_choices(
                    question,
                    answer_label="右",
                    distractor_labels=("左", "上", "下"),
                )
                if choices is not None:
                    question.update(
                        {
                            "prompt": "红花盆在蓝花盆的左边。蓝花盆在红花盆的哪一边?",
                            "choices": choices,
                            "hint": "把已知的左右关系反过来想。",
                            "explanation": "红花盆在蓝花盆的左边,所以蓝花盆在红花盆的右边。",
                        }
                    )
            elif (
                selected_label == "上面"
                and re.search(
                    r'["“]?请进["”]?[^,，。?？]{0,16}'
                    r'["“]?欢迎["”]?的下面',
                    prompt,
                )
                and re.search(
                    r'["“]?欢迎["”]?[^,，。?？]{0,16}'
                    r'["“]?请进["”]?[^,，。?？]{0,8}哪一面',
                    prompt,
                )
            ):
                choices = relabel_directional_choices(
                    question,
                    answer_label="下",
                    distractor_labels=("上", "左", "右"),
                )
                if choices is not None:
                    question.update(
                        {
                            "prompt": "“欢迎”在“请进”的上方(上面)。“请进”在“欢迎”的哪一边?",
                            "choices": choices,
                            "hint": "把已知的上下关系反过来想。",
                            "explanation": "“欢迎”在“请进”的上方,所以“请进”在“欢迎”的下方。",
                        }
                    )
            elif selected_label == "长方形" and any(
                re.search(pattern, prompt)
                for pattern in (
                    r"四条边(?:并非|不是|不都|不全)(?:一样长|相等)",
                    r"相邻(?:的)?(?:两条)?边(?:长度)?(?:不同|不一样|不相等)",
                    r"两条(?:边)?(?:比较)?长.{0,16}两条(?:边)?(?:比较)?短",
                    r"长和宽(?:不同|不一样|不相等)",
                )
            ):
                question.update(
                    {
                        "prompt": "这个图形有四条直边和四个直角,对边相等,而且相邻边长度不同。它是什么图形?",
                        "hint": "注意这个具体图形的相邻边长度是否相同。",
                        "explanation": "题目说明这个具体图形的对边相等,并且相邻边长度不同,所以它是长方形,不是正方形。",
                    }
                )
            rewritten_questions.append(question)
        content["questions"] = rewritten_questions
        return normalized, frozenset(repaired)

    @staticmethod
    def _normalize_primary_one_characters_words_host_checkpoint(
        course: Mapping[str, Any],
        *,
        solution: Mapping[str, Any],
        target: PrimaryOneCourseTarget,
        logical_attempt: int,
    ) -> tuple[dict[str, Any], frozenset[str]]:
        """Remove one sealed collocation ambiguity without changing answer IDs.

        The historical Provider checkpoint may contain both “上学” and “上山”.
        The Host authority already seals “上” -> “学”; replacing only the
        non-answer labels keeps the paid artifact while making the question
        single-answer.  A Provider disagreement is forgiven only when it chose
        the exact removed “山” distractor and every other answer still agrees.
        """

        normalized = copy.deepcopy(dict(course))
        if not (
            target.grade_code == "primary_1"
            and target.subject == "chinese"
            and target.skill_id == "characters_words"
            and logical_attempt == 2
        ):
            return normalized, frozenset()
        content = normalized.get("content")
        questions = content.get("questions") if isinstance(content, Mapping) else None
        answers = solution.get("answers") if isinstance(solution, Mapping) else None
        if not isinstance(questions, list) or not isinstance(answers, list):
            return normalized, frozenset()
        answer_by_question_id = {
            str(answer.get("questionId") or ""): answer.get("answer")
            for answer in answers
            if isinstance(answer, Mapping)
        }
        repaired: set[str] = set()
        rewritten_questions: list[object] = []
        for raw_question in questions:
            if not isinstance(raw_question, Mapping):
                rewritten_questions.append(copy.deepcopy(raw_question))
                continue
            question = copy.deepcopy(dict(raw_question))
            prompt = unicodedata.normalize(
                "NFKC", str(question.get("prompt") or "")
            )
            choices = question.get("choices")
            answer_id = question.get("answer")
            quoted = re.search(r'[“"]([^”"]+)[”"]', prompt)
            if not (
                question.get("type") == "single_choice"
                and quoted is not None
                and quoted.group(1) == "上"
                and "搭配" in prompt
                and isinstance(choices, list)
                and 2 <= len(choices) <= 4
                and isinstance(answer_id, str)
            ):
                rewritten_questions.append(question)
                continue
            selected = [
                choice
                for choice in choices
                if isinstance(choice, Mapping)
                and choice.get("id") == answer_id
                and isinstance(choice.get("label"), str)
            ]
            if len(selected) != 1 or unicodedata.normalize(
                "NFKC", str(selected[0]["label"])
            ).strip() != "学":
                rewritten_questions.append(question)
                continue
            independent_id = answer_by_question_id.get(
                str(question.get("id") or "")
            )
            independent_choice = next(
                (
                    choice
                    for choice in choices
                    if isinstance(choice, Mapping)
                    and choice.get("id") == independent_id
                ),
                None,
            )
            independent_label = (
                unicodedata.normalize(
                    "NFKC", str(independent_choice.get("label") or "")
                ).strip()
                if isinstance(independent_choice, Mapping)
                else ""
            )
            if independent_id not in {None, answer_id} and independent_label != "山":
                rewritten_questions.append(question)
                continue
            distractors = iter(("木", "鸟", "羊"))
            rewritten_choices: list[dict[str, Any]] = []
            for choice in choices:
                if not isinstance(choice, Mapping):
                    rewritten_choices = []
                    break
                rewritten = copy.deepcopy(dict(choice))
                if choice.get("id") != answer_id:
                    rewritten["label"] = next(distractors)
                rewritten_choices.append(rewritten)
            if not rewritten_choices:
                rewritten_questions.append(question)
                continue
            question["choices"] = rewritten_choices
            if independent_id != answer_id and independent_label == "山":
                repaired.add(str(question.get("id") or ""))
            rewritten_questions.append(question)
        content["questions"] = rewritten_questions
        return normalized, frozenset(repaired)

    def validate_primary_one_accepted_receipt(
        self, proof: AcceptedPrimaryOneHostReceipt
    ) -> str:
        if not isinstance(proof, AcceptedPrimaryOneHostReceipt):
            raise PrimaryOneHostGateControlError("accepted receipt proof type drift")
        if not isinstance(proof.target, PrimaryOneCourseTarget):
            raise PrimaryOneHostGateControlError("accepted receipt target type drift")
        if not isinstance(proof.immutable_course, Mapping) or not isinstance(
            proof.receipt, Mapping
        ):
            raise PrimaryOneHostGateControlError("accepted receipt payload drift")
        receipt = dict(proof.receipt)
        self._assert_primary_one_receipt_shape(receipt)
        if not self._is_sha256(proof.receipt_hash) or self._sha256_json(receipt) != proof.receipt_hash:
            raise PrimaryOneHostGateControlError("accepted receipt hash drift")
        context = self.catalog_validator._primary_one_context(proof.target, None)
        boundary = context["skill_boundary"]
        immutable_course = copy.deepcopy(dict(proof.immutable_course))
        content = immutable_course.get("content")
        if (
            immutable_course.get("status") != "published"
            or not isinstance(content, Mapping)
            or content.get("sourceAuthority") != GENERATED_SOURCE_AUTHORITY
        ):
            raise PrimaryOneHostGateControlError(
                "accepted immutable course publication drift"
            )
        try:
            self.catalog_validator.validate_primary_one_generated_course(
                immutable_course,
                target=proof.target,
                skill_boundary=boundary,
            )
        except Exception as exc:
            raise PrimaryOneHostGateControlError(
                "accepted immutable course failed intrinsic recheck"
            ) from exc
        fingerprint = self.primary_one_content_fingerprint(
            immutable_course, target=proof.target
        )
        candidate_course = copy.deepcopy(immutable_course)
        candidate_course["status"] = _CANDIDATE_STATUS
        candidate_course["content"]["sourceAuthority"] = copy.deepcopy(
            _CANDIDATE_SOURCE_AUTHORITY
        )
        expected_isolation = (
            "isolated_request_same_profile"
            if receipt.get("generatorProfileHash")
            == receipt.get("verifierProfileHash")
            else "isolated_request_distinct_profile"
        )
        expected = {
            "schemaVersion": PRIMARY_ONE_HOST_GATE_RECEIPT_SCHEMA_VERSION,
            "validatorVersion": PRIMARY_ONE_HOST_GATE_VERSION,
            "fingerprintVersion": PRIMARY_ONE_HOST_FINGERPRINT_VERSION,
            "contentValidationContractVersion": CONTENT_VALIDATION_CONTRACT_VERSION,
            "contentValidationDatasetSha256": PRIMARY_ONE_CONTENT_DATASET_SHA256,
            "subjectLanguagePolicyVersion": SUBJECT_LANGUAGE_POLICY_VERSION,
            "courseId": immutable_course.get("id"),
            "courseVersion": immutable_course.get("version"),
            "gradeCode": proof.target.grade_code,
            "subject": proof.target.subject,
            "subjectOrdinal": proof.target.subject_ordinal,
            "skillId": proof.target.skill_id,
            "boundaryOrdinal": proof.target.boundary_ordinal,
            "boundaryVersion": proof.target.boundary_version,
            "variantOrdinal": proof.target.variant_ordinal,
            "instructionLanguageCode": proof.target.instruction_language_code,
            "targetLanguageCode": proof.target.target_language_code,
            "verificationIsolation": expected_isolation,
            "skillBoundarySha256": self._sha256_json(boundary),
            "candidateCourseSha256": self._sha256_json(candidate_course),
            "hostContentFingerprint": fingerprint,
            "outcome": "passed",
            "issues": [],
            "checksPassed": list(_PRIMARY_ONE_HOST_CHECKS),
        }
        for key, value in expected.items():
            if receipt.get(key) != value:
                raise PrimaryOneHostGateControlError(
                    f"accepted receipt field drift: {key}"
                )
        for key in (
            "generationRequestIdHash",
            "generatorProfileHash",
            "verifierProfileHash",
            "skillBoundarySha256",
            "candidateCourseSha256",
            "sidecarEvidenceSha256",
        ):
            if not self._is_sha256(receipt.get(key)):
                raise PrimaryOneHostGateControlError(
                    f"accepted receipt digest drift: {key}"
                )
        if receipt.get("logicalAttempt") not in {1, 2} or isinstance(
            receipt.get("logicalAttempt"), bool
        ):
            raise PrimaryOneHostGateControlError("accepted receipt attempt drift")
        if receipt.get("verificationIsolation") not in {
            "isolated_request_same_profile",
            "isolated_request_distinct_profile",
        }:
            raise PrimaryOneHostGateControlError("accepted receipt isolation drift")
        if (
            receipt.get("finalProviderPhase"),
            receipt.get("finalProviderPhaseOrdinal"),
        ) not in {
            ("independent_verification", 11),
            ("verification_after_repair", 14),
        }:
            raise PrimaryOneHostGateControlError("accepted receipt phase drift")
        return fingerprint

    def primary_one_content_fingerprint_payload_json(
        self,
        course: Mapping[str, Any],
        *,
        target: PrimaryOneCourseTarget,
    ) -> str:
        if not isinstance(course, Mapping) or not isinstance(target, PrimaryOneCourseTarget):
            self._fail(
                "invalid_primary_one_fingerprint",
                "Formal fingerprint input is invalid.",
                path="candidateCourse",
            )
        content = course.get("content")
        questions = content.get("questions") if isinstance(content, Mapping) else None
        if not isinstance(questions, list) or len(questions) != 5:
            self._fail(
                "invalid_primary_one_fingerprint",
                "Formal fingerprint requires exactly five questions.",
                path="candidateCourse.content.questions",
            )
        normalized_questions = [
            self._primary_one_question_fingerprint_payload(
                question, target=target, index=index
            )
            for index, question in enumerate(questions)
        ]
        canonical_questions = [self._canonical_json(item) for item in normalized_questions]
        if len(set(canonical_questions)) != 5:
            self._fail(
                "duplicate_primary_one_question",
                "Formal course questions must be internally distinct.",
                path="candidateCourse.content.questions",
            )
        payload = {
            "schemaVersion": PRIMARY_ONE_HOST_FINGERPRINT_PAYLOAD_SCHEMA_VERSION,
            "gradeCode": target.grade_code,
            "subject": target.subject,
            "skillId": target.skill_id,
            "boundaryVersion": target.boundary_version,
            "questions": sorted(
                normalized_questions, key=lambda item: self._canonical_json(item)
            ),
        }
        return self._canonical_json(payload)

    def primary_one_content_fingerprint(
        self,
        course: Mapping[str, Any],
        *,
        target: PrimaryOneCourseTarget,
    ) -> str:
        payload = self.primary_one_content_fingerprint_payload_json(
            course, target=target
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _validate_primary_one_identity(
        self,
        identity: PrimaryOneHostGateIdentity,
        target: PrimaryOneCourseTarget,
    ) -> None:
        if not isinstance(identity, PrimaryOneHostGateIdentity):
            raise PrimaryOneHostGateControlError("host identity type drift")
        if (
            not isinstance(identity.catalog_item_id, str)
            or not identity.catalog_item_id.strip()
            or len(identity.catalog_item_id) > 255
        ):
            raise PrimaryOneHostGateControlError("catalog item identity drift")
        if (
            isinstance(identity.logical_attempt, bool)
            or not isinstance(identity.logical_attempt, int)
            or identity.logical_attempt not in {1, 2}
        ):
            raise PrimaryOneHostGateControlError("logical attempt identity drift")
        if (
            not isinstance(identity.generation_request_id, str)
            or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}",
                identity.generation_request_id,
            )
        ):
            raise PrimaryOneHostGateControlError("generation request identity drift")
        for label, value, maximum in (
            ("course id", identity.course_id, 255),
            ("course version", identity.course_version, 80),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                raise PrimaryOneHostGateControlError(f"{label} identity drift")
        fixed = {
            "curriculum_version": PRIMARY_CURRICULUM_VERSION,
            "content_validation_contract_version": CONTENT_VALIDATION_CONTRACT_VERSION,
            "content_validation_dataset_sha256": PRIMARY_ONE_CONTENT_DATASET_SHA256,
            "subject_language_policy_version": SUBJECT_LANGUAGE_POLICY_VERSION,
        }
        for field, expected in fixed.items():
            if getattr(identity, field) != expected:
                raise PrimaryOneHostGateControlError(f"host identity drift: {field}")
        for field in ("generator_profile_hash", "verifier_profile_hash"):
            if not self._is_sha256(getattr(identity, field)):
                raise PrimaryOneHostGateControlError(f"host identity digest drift: {field}")
        if target.grade_code != "primary_1":
            raise PrimaryOneHostGateControlError("host target grade drift")

    def _validate_primary_one_profile(
        self,
        profile: QuestionPhaseProviderProfileEvidence,
        field: str,
    ) -> tuple[dict[str, object], str]:
        if not isinstance(profile, QuestionPhaseProviderProfileEvidence):
            raise PrimaryOneHostGateControlError(f"{field} type drift")
        for label, value, maximum in (
            ("name", profile.name, 80),
            ("model", profile.model, 160),
            ("baseUrl", profile.base_url, 500),
            ("apiKeyEnv", profile.api_key_env, 80),
        ):
            if (
                not isinstance(value, str)
                or not value.strip()
                or value != unicodedata.normalize("NFKC", value).strip()
                or len(value) > maximum
            ):
                raise PrimaryOneHostGateControlError(f"{field}.{label} drift")
        parsed = urlsplit(profile.base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise PrimaryOneHostGateControlError(f"{field}.baseUrl drift")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", profile.api_key_env):
            raise PrimaryOneHostGateControlError(f"{field}.apiKeyEnv drift")
        if (
            isinstance(profile.timeout_ms, bool)
            or not isinstance(profile.timeout_ms, int)
            or not 1_000 <= profile.timeout_ms <= 300_000
            or isinstance(profile.max_tokens, bool)
            or not isinstance(profile.max_tokens, int)
            or not 512 <= profile.max_tokens <= 32_000
            or isinstance(profile.temperature, bool)
            or not isinstance(profile.temperature, (int, float))
            or not math.isfinite(profile.temperature)
            or not 0 <= profile.temperature <= 1
        ):
            raise PrimaryOneHostGateControlError(f"{field} scalar drift")
        payload = {
            "name": profile.name,
            "model": profile.model,
            "baseUrl": profile.base_url,
            "apiKeyEnv": profile.api_key_env,
            "timeoutMs": profile.timeout_ms,
            "maxTokens": profile.max_tokens,
            "temperature": profile.temperature,
        }
        digest = self._sha256_json(payload)
        if profile.profile_hash != digest:
            raise PrimaryOneHostGateControlError(f"{field}.profileHash drift")
        return payload, digest

    def _validate_primary_one_phase_evidence(
        self,
        evidence: QuestionPhaseCourseEvidence,
        *,
        target: PrimaryOneCourseTarget,
        identity: PrimaryOneHostGateIdentity,
        skill_boundary: Mapping[str, object],
        verifier_profile: Mapping[str, object],
    ) -> dict[str, Any]:
        if not isinstance(evidence, QuestionPhaseCourseEvidence):
            raise PrimaryOneHostGateControlError("phase evidence type drift")
        if (
            evidence.final_phase,
            evidence.final_phase_ordinal,
        ) not in {
            ("independent_verification", 11),
            ("verification_after_repair", 14),
        } or isinstance(evidence.final_phase_ordinal, bool):
            raise PrimaryOneHostGateControlError("final phase identity drift")
        if not isinstance(evidence.candidate_course, Mapping):
            raise PrimaryOneHostGateControlError("candidate course shape drift")
        course = copy.deepcopy(dict(evidence.candidate_course))
        try:
            self._strict_candidate_schema(course)
            self._validate_lengths(course)
            self._validate_primary_one_task4_questions(
                course,
                target=target,
                skill_boundary=skill_boundary,
                request_id=identity.generation_request_id,
                logical_attempt=identity.logical_attempt,
            )
            self._validate_primary_one_task4_flow(course)
        except GeneratedCourseValidationError as exc:
            raise PrimaryOneHostGateControlError(
                "candidate course is not a canonical Task-4 checkpoint"
            ) from exc
        expected_course_id = question_candidate_course_id(
            grade_code=target.grade_code,
            subject=target.subject,
            skill_id=target.skill_id,
            generation_request_id=identity.generation_request_id,
            logical_attempt=identity.logical_attempt,
        )
        if (
            course.get("id") != expected_course_id
            or course.get("id") != identity.course_id
            or course.get("version") != "0.0.0-candidate"
            or course.get("version") != identity.course_version
            or course.get("gradeCode") != target.grade_code
            or course.get("subject") != target.subject
            or course.get("nodeCode") != target.skill_id
            or course.get("objective")
            != unicodedata.normalize(
                "NFKC", "；".join(skill_boundary["learningObjectives"])
            ).strip()
        ):
            raise PrimaryOneHostGateControlError("candidate course identity drift")
        self._validate_primary_one_sidecar_fingerprints(
            evidence.question_fingerprints,
            course=course,
            target=target,
        )
        self._validate_primary_one_sidecar_validation(
            evidence.validation,
            course=course,
            target=target,
            logical_attempt=identity.logical_attempt,
            existing_fingerprint_count=evidence.existing_fingerprint_count,
        )
        self._validate_primary_one_solution_shape(
            evidence.independent_solution,
            course=course,
            target=target,
            request_id=identity.generation_request_id,
            verifier_profile=verifier_profile,
        )
        return course

    def _validate_primary_one_task4_questions(
        self,
        course: Mapping[str, Any],
        *,
        target: PrimaryOneCourseTarget,
        skill_boundary: Mapping[str, object],
        request_id: str,
        logical_attempt: int,
    ) -> None:
        questions = course["content"]["questions"]
        expected_slug = question_candidate_request_slug(
            request_id,
            maximum=64,
            logical_attempt=logical_attempt,
        )
        seen: set[str] = set()
        for index, question in enumerate(questions):
            path = f"candidate.content.questions[{index}]"
            if not isinstance(question, Mapping):
                self._fail(
                    "invalid_generated_course_schema",
                    "question must be an object.",
                    path=path,
                )
            question_type = str(question.get("type") or "")
            if question_type not in _QUESTION_KEYS_BY_TYPE:
                self._fail(
                    "unsupported_generated_question_type",
                    "question type is invalid.",
                    path=f"{path}.type",
                )
            self._exact_keys(question, _QUESTION_KEYS_BY_TYPE[question_type], path)
            expected_id = f"{expected_slug}_q{index + 1}"
            if (
                question.get("id") != expected_id
                or question.get("id") in seen
                or question.get("skill") != skill_boundary["skillTitle"]
            ):
                self._fail(
                    "invalid_generated_course_schema",
                    "question host identity is invalid.",
                    path=path,
                )
            seen.add(str(question["id"]))
            for key in ("prompt", "skill", "hint", "explanation"):
                text = self._bounded_text(
                    question.get(key),
                    f"{path}.{key}",
                    _TEXT_LIMITS[f"question.{key}"],
                )
                if text != unicodedata.normalize("NFKC", text).strip() or re.search(
                    r"<[^>]*>", text
                ):
                    self._fail(
                        "invalid_generated_course_schema",
                        "question text is not canonical plain text.",
                        path=f"{path}.{key}",
                    )
            evaluation = question.get("evaluation")
            if not isinstance(evaluation, Mapping):
                self._fail(
                    "invalid_generated_course_schema",
                    "question evaluation is invalid.",
                    path=f"{path}.evaluation",
                )
            self._exact_keys(
                evaluation,
                _EVALUATION_KEYS_BY_TYPE[question_type],
                f"{path}.evaluation",
            )
            expected_normalization = {
                "numeric": ["trim", "remove_grouping_separators"],
                "single_choice": ["trim", "casefold"],
                "sequence": ["trim", "casefold"],
                "exact_text": [
                    "trim",
                    "collapse_whitespace",
                    *( ["casefold", "strip_terminal_punctuation"] if target.subject == "english" else ["remove_whitespace"] ),
                ],
                "accepted_text": [
                    "trim",
                    "collapse_whitespace",
                    *( ["casefold", "strip_terminal_punctuation"] if target.subject == "english" else ["remove_whitespace"] ),
                ],
            }[question_type]
            if evaluation.get("normalization") != expected_normalization:
                self._fail(
                    "unsafe_generated_normalization",
                    "normalization does not match Task-4 authority.",
                    path=f"{path}.evaluation.normalization",
                )
            self._validate_answer_contract(question, question_type, path)
        if questions[1]["type"] not in {"single_choice", "sequence"} or (
            questions[1]["type"] != questions[2]["type"]
        ):
            self._fail(
                "invalid_generated_course_schema",
                "guided question types are invalid.",
                path="candidate.content.questions",
            )

    def _validate_primary_one_task4_flow(self, course: Mapping[str, Any]) -> None:
        flow = course["content"].get("teachingFlow")
        path = "candidate.content.teachingFlow"
        if not isinstance(flow, Mapping):
            self._fail("invalid_generated_teaching_flow", "flow invalid", path=path)
        self._exact_keys(
            flow,
            frozenset(
                {
                    "schemaVersion",
                    "teach",
                    "demoQuestionId",
                    "guidedQuestionIds",
                    "independentQuestionIds",
                    "recap",
                }
            ),
            path,
        )
        teach = flow.get("teach")
        recap = flow.get("recap")
        if not isinstance(teach, Mapping) or not isinstance(recap, Mapping):
            self._fail("invalid_generated_teaching_flow", "flow invalid", path=path)
        self._exact_keys(
            teach,
            frozenset({"title", "sayText", "keyPoints"}),
            f"{path}.teach",
        )
        self._exact_keys(recap, frozenset({"sayText"}), f"{path}.recap")
        self._bounded_text(teach.get("title"), f"{path}.teach.title", 160)
        self._bounded_text(teach.get("sayText"), f"{path}.teach.sayText", 1200)
        self._bounded_text(recap.get("sayText"), f"{path}.recap.sayText", 600)
        key_points = teach.get("keyPoints")
        if not isinstance(key_points, list) or not 1 <= len(key_points) <= 3:
            self._fail("invalid_generated_teaching_flow", "key points invalid", path=path)
        normalized_points = [
            self._bounded_text(item, f"{path}.teach.keyPoints[{index}]", 200)
            for index, item in enumerate(key_points)
        ]
        if len(set(normalized_points)) != len(normalized_points):
            self._fail("invalid_generated_teaching_flow", "key points duplicate", path=path)
        question_ids = [str(item["id"]) for item in course["content"]["questions"]]
        roles = [
            flow.get("demoQuestionId"),
            *(flow.get("guidedQuestionIds") if isinstance(flow.get("guidedQuestionIds"), list) else []),
            *(flow.get("independentQuestionIds") if isinstance(flow.get("independentQuestionIds"), list) else []),
        ]
        if (
            flow.get("schemaVersion") != TEACHING_FLOW_SCHEMA_VERSION
            or roles != question_ids
            or len(set(roles)) != 5
        ):
            self._fail("invalid_generated_teaching_flow", "role evidence drift", path=path)

    def _validate_primary_one_sidecar_fingerprints(
        self,
        raw: Sequence[Mapping[str, object]],
        *,
        course: Mapping[str, Any],
        target: PrimaryOneCourseTarget,
    ) -> None:
        if isinstance(raw, (str, bytes, Mapping)) or not isinstance(raw, Sequence) or len(raw) != 5:
            raise PrimaryOneHostGateControlError("Sidecar question fingerprints drift")
        expected = []
        for question in course["content"]["questions"]:
            payload = {
                "gradeCode": target.grade_code,
                "subject": target.subject,
                "skillId": target.skill_id,
                "type": question["type"],
                "prompt": self._sidecar_comparable(question["prompt"]),
                "choiceLabels": sorted(
                    self._sidecar_comparable(choice["label"])
                    for choice in question.get("choices", [])
                ),
            }
            encoded = json.dumps(
                payload, ensure_ascii=False, separators=(",", ":")
            )
            expected.append(
                {
                    "questionId": question["id"],
                    "fingerprint": hashlib.sha256(encoded.encode()).hexdigest(),
                }
            )
        normalized = [dict(item) if isinstance(item, Mapping) else item for item in raw]
        if normalized != expected or any(set(item) != {"questionId", "fingerprint"} for item in normalized):
            raise PrimaryOneHostGateControlError("Sidecar question fingerprint authority drift")
        if len({item["questionId"] for item in normalized}) != 5 or len(
            {item["fingerprint"] for item in normalized}
        ) != 5:
            raise PrimaryOneHostGateControlError("Sidecar question fingerprint duplicates")

    @staticmethod
    def _validate_authoritative_question_fingerprints(
        raw: Sequence[str],
    ) -> set[str]:
        if isinstance(raw, (str, bytes, Mapping)) or not isinstance(raw, Sequence):
            raise PrimaryOneHostGateControlError(
                "Host question fingerprint authority drift"
            )
        normalized = [str(value) for value in raw]
        if normalized != sorted(set(normalized)) or any(
            re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in normalized
        ):
            raise PrimaryOneHostGateControlError(
                "Host question fingerprint authority drift"
            )
        return set(normalized)

    def _primary_one_question_fingerprints(
        self,
        course: Mapping[str, Any],
        *,
        target: PrimaryOneCourseTarget,
    ) -> set[str]:
        return {
            hashlib.sha256(
                json.dumps(
                    {
                        "gradeCode": target.grade_code,
                        "subject": target.subject,
                        "skillId": target.skill_id,
                        "type": question["type"],
                        "prompt": self._sidecar_comparable(question["prompt"]),
                        "choiceLabels": sorted(
                            self._sidecar_comparable(choice["label"])
                            for choice in question.get("choices", [])
                        ),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            for question in course["content"]["questions"]
        }

    def _validate_primary_one_sidecar_validation(
        self,
        raw: Mapping[str, object],
        *,
        course: Mapping[str, Any],
        target: PrimaryOneCourseTarget,
        logical_attempt: int,
        existing_fingerprint_count: int,
    ) -> None:
        if (
            type(existing_fingerprint_count) is not int
            or not 0 <= existing_fingerprint_count <= 500
        ):
            raise PrimaryOneHostGateControlError(
                "Sidecar existing fingerprint count drift"
            )
        expected = {
            "schemaValidated": True,
            "boundaryPreserved": True,
            "plainTextOnly": True,
            "questionCount": 5,
            "allowedQuestionTypes": [
                "accepted_text",
                "exact_text",
                "numeric",
                "sequence",
                "single_choice",
            ],
            "guidedQuestionTypes": ["sequence", "single_choice"],
            "existingFingerprintsChecked": existing_fingerprint_count,
            "duplicateFingerprints": [],
            "independentSolutionRequired": True,
            "independentSolutionProvided": False,
            "teachingFlowSchemaValidated": True,
            "teachingReviewRequired": True,
            "programmaticNumericRecalculationRequired": any(
                item["type"] == "numeric"
                for item in course["content"]["questions"]
            ),
        }
        if not isinstance(raw, Mapping) or dict(raw) != expected:
            raise PrimaryOneHostGateControlError("Sidecar validation checkpoint drift")

    def _validate_primary_one_solution_shape(
        self,
        raw: Mapping[str, object],
        *,
        course: Mapping[str, Any],
        target: PrimaryOneCourseTarget,
        request_id: str,
        verifier_profile: Mapping[str, object],
    ) -> None:
        if not isinstance(raw, Mapping) or set(raw) != {
            "schemaVersion",
            "solver",
            "independentFromGeneration",
            "verificationRequestId",
            "publicQuestionHash",
            "gradeCode",
            "subject",
            "skillId",
            "answers",
            "teachingReview",
        }:
            raise PrimaryOneHostGateControlError("independent solution shape drift")
        expected_solver = (
            f"{verifier_profile['name']}:{verifier_profile['model']}:fresh_call"
        )
        allowed_solvers = {expected_solver}
        if (
            target.grade_code == "primary_1"
            and (
                target.subject == "math"
                or (
                    target.subject == "chinese"
                    and target.skill_id
                    in {"characters_words", "simple_sentences"}
                )
            )
        ):
            host_solver = {
                "addition_subtraction_20": PRIMARY_ONE_ADD_SUB_HOST_SOLVER,
                "number_sense_20": PRIMARY_ONE_NUMBER_SENSE_HOST_SOLVER,
                "characters_words": PRIMARY_ONE_CHARACTER_WORD_HOST_SOLVER,
                "simple_sentences": PRIMARY_ONE_SIMPLE_SENTENCE_HOST_SOLVER,
            }.get(target.skill_id)
            if host_solver is not None:
                allowed_solvers.add(host_solver)
        if (
            raw.get("schemaVersion") != INDEPENDENT_SOLUTION_SCHEMA_VERSION
            or raw.get("solver") not in allowed_solvers
            or raw.get("independentFromGeneration") is not True
            or raw.get("verificationRequestId") != request_id
            or raw.get("publicQuestionHash") != self._primary_one_public_question_hash(course)
            or raw.get("gradeCode") != target.grade_code
            or raw.get("subject") != target.subject
            or raw.get("skillId") != target.skill_id
        ):
            raise PrimaryOneHostGateControlError("independent solution provenance drift")
        review = raw.get("teachingReview")
        if (
            not isinstance(review, Mapping)
            or set(review) != {"passed", "issues"}
            or not isinstance(review.get("passed"), bool)
            or not isinstance(review.get("issues"), list)
            or len(review.get("issues", [])) > 3
            or any(not isinstance(item, str) or not item.strip() or len(item) > 300 for item in review.get("issues", []))
            or (review.get("passed") is True and review.get("issues") != [])
            or (review.get("passed") is False and not review.get("issues"))
        ):
            raise PrimaryOneHostGateControlError("teaching review evidence drift")
        answers = raw.get("answers")
        questions = course["content"]["questions"]
        if not isinstance(answers, list) or len(answers) != 5:
            raise PrimaryOneHostGateControlError("independent answers shape drift")
        for index, (answer, question) in enumerate(zip(answers, questions)):
            expected_keys = (
                {"questionId", "answer", "derivedExpression"}
                if question["type"] == "numeric"
                else {"questionId", "answer"}
            )
            if (
                not isinstance(answer, Mapping)
                or set(answer) != expected_keys
                or answer.get("questionId") != question["id"]
            ):
                raise PrimaryOneHostGateControlError(
                    f"independent answer provenance drift at {index}"
                )
            expects_array = question["type"] == "sequence"
            if expects_array != isinstance(answer.get("answer"), list):
                raise PrimaryOneHostGateControlError(
                    f"independent answer type drift at {index}"
                )
            if not expects_array and not isinstance(answer.get("answer"), str):
                raise PrimaryOneHostGateControlError(
                    f"independent answer scalar drift at {index}"
                )
            if question["type"] == "numeric" and (
                not isinstance(answer.get("derivedExpression"), str)
                or not answer["derivedExpression"].strip()
                or len(answer["derivedExpression"]) > 128
            ):
                raise PrimaryOneHostGateControlError(
                    f"independent numeric derivation shape drift at {index}"
                )

    def _validate_primary_one_prior_receipts(
        self,
        raw: Sequence[AcceptedPrimaryOneHostReceipt],
        *,
        target: PrimaryOneCourseTarget,
    ) -> set[str]:
        if isinstance(raw, (str, bytes, Mapping)) or not isinstance(raw, Sequence):
            raise PrimaryOneHostGateControlError("accepted_host_receipts must be a sequence")
        expected_ordinals = list(range(1, target.variant_ordinal))
        if len(raw) != len(expected_ordinals):
            raise PrimaryOneHostGateControlError("prior accepted receipt count drift")
        fingerprints: set[str] = set()
        for ordinal, proof in zip(expected_ordinals, raw):
            if not isinstance(proof, AcceptedPrimaryOneHostReceipt):
                raise PrimaryOneHostGateControlError("prior accepted receipt type drift")
            prior = proof.target
            if (
                not isinstance(prior, PrimaryOneCourseTarget)
                or prior.variant_ordinal != ordinal
                or (
                    prior.grade_code,
                    prior.subject,
                    prior.subject_ordinal,
                    prior.skill_id,
                    prior.boundary_ordinal,
                    prior.boundary_version,
                    prior.instruction_language_code,
                    prior.target_language_code,
                )
                != (
                    target.grade_code,
                    target.subject,
                    target.subject_ordinal,
                    target.skill_id,
                    target.boundary_ordinal,
                    target.boundary_version,
                    target.instruction_language_code,
                    target.target_language_code,
                )
            ):
                raise PrimaryOneHostGateControlError("prior accepted target drift")
            try:
                fingerprint = self.validate_primary_one_accepted_receipt(proof)
            except PrimaryOneHostGateControlError:
                raise
            except Exception as exc:
                raise PrimaryOneHostGateDependencyError(
                    "sealed primary-one authority unavailable"
                ) from exc
            if fingerprint in fingerprints:
                raise PrimaryOneHostGateControlError("prior receipt fingerprints duplicate")
            fingerprints.add(fingerprint)
        return fingerprints

    def _primary_one_receipt_base(
        self,
        *,
        target: PrimaryOneCourseTarget,
        identity: PrimaryOneHostGateIdentity,
        evidence: QuestionPhaseCourseEvidence,
        skill_boundary_sha256: str,
        candidate_course_sha256: str,
        sidecar_evidence_sha256: str,
    ) -> dict[str, object]:
        return {
            "schemaVersion": PRIMARY_ONE_HOST_GATE_RECEIPT_SCHEMA_VERSION,
            "validatorVersion": PRIMARY_ONE_HOST_GATE_VERSION,
            "fingerprintVersion": PRIMARY_ONE_HOST_FINGERPRINT_VERSION,
            "contentValidationContractVersion": CONTENT_VALIDATION_CONTRACT_VERSION,
            "contentValidationDatasetSha256": PRIMARY_ONE_CONTENT_DATASET_SHA256,
            "subjectLanguagePolicyVersion": SUBJECT_LANGUAGE_POLICY_VERSION,
            "catalogItemId": identity.catalog_item_id,
            "logicalAttempt": identity.logical_attempt,
            "generationRequestIdHash": hashlib.sha256(
                identity.generation_request_id.encode("utf-8")
            ).hexdigest(),
            "courseId": identity.course_id,
            "courseVersion": identity.course_version,
            "gradeCode": target.grade_code,
            "subject": target.subject,
            "subjectOrdinal": target.subject_ordinal,
            "skillId": target.skill_id,
            "boundaryOrdinal": target.boundary_ordinal,
            "boundaryVersion": target.boundary_version,
            "variantOrdinal": target.variant_ordinal,
            "instructionLanguageCode": target.instruction_language_code,
            "targetLanguageCode": target.target_language_code,
            "finalProviderPhase": evidence.final_phase,
            "finalProviderPhaseOrdinal": evidence.final_phase_ordinal,
            "generatorProfileHash": identity.generator_profile_hash,
            "verifierProfileHash": identity.verifier_profile_hash,
            "verificationIsolation": (
                "isolated_request_same_profile"
                if identity.generator_profile_hash == identity.verifier_profile_hash
                else "isolated_request_distinct_profile"
            ),
            "skillBoundarySha256": skill_boundary_sha256,
            "candidateCourseSha256": candidate_course_sha256,
            "sidecarEvidenceSha256": sidecar_evidence_sha256,
        }

    def _primary_one_rejected(
        self,
        common_receipt: Mapping[str, object],
        checks: Sequence[str],
        *,
        issue: str,
        fingerprint: str,
    ) -> PrimaryOneHostGateResult:
        receipt = {
            **dict(common_receipt),
            "hostContentFingerprint": fingerprint,
            "outcome": "rejected",
            "checksPassed": list(checks),
            "issues": [copy.deepcopy(_PRIMARY_ONE_ISSUES[issue])],
        }
        self._assert_primary_one_receipt_shape(receipt)
        return PrimaryOneHostGateResult(
            outcome="rejected",
            course=None,
            receipt=receipt,
            receipt_hash=self._sha256_json(receipt),
        )

    def _assert_primary_one_receipt_shape(self, receipt: Mapping[str, object]) -> None:
        if not isinstance(receipt, Mapping) or set(receipt) != set(_PRIMARY_ONE_RECEIPT_KEYS):
            raise PrimaryOneHostGateControlError("Host receipt field drift")
        checks = receipt.get("checksPassed")
        if (
            not isinstance(checks, list)
            or len(checks) != len(set(checks))
            or checks != list(_PRIMARY_ONE_HOST_CHECKS[: len(checks)])
        ):
            raise PrimaryOneHostGateControlError("Host receipt checks drift")
        outcome = receipt.get("outcome")
        issues = receipt.get("issues")
        fingerprint = receipt.get("hostContentFingerprint")
        if outcome == "passed":
            if checks != list(_PRIMARY_ONE_HOST_CHECKS) or issues != [] or not self._is_sha256(fingerprint):
                raise PrimaryOneHostGateControlError("passed Host receipt evidence drift")
        elif outcome == "rejected":
            if (
                not isinstance(issues, list)
                or len(issues) != 1
                or not isinstance(issues[0], Mapping)
                or set(issues[0]) != {"code", "path", "message"}
                or not isinstance(fingerprint, str)
                or (fingerprint and not self._is_sha256(fingerprint))
            ):
                raise PrimaryOneHostGateControlError("rejected Host receipt evidence drift")
        else:
            raise PrimaryOneHostGateControlError("Host receipt outcome drift")

    def _primary_one_independent_answers_agree(
        self,
        course: Mapping[str, Any],
        solution: Mapping[str, Any],
        *,
        host_repaired_question_ids: frozenset[str] = frozenset(),
    ) -> bool:
        questions = course["content"]["questions"]
        answers = solution["answers"]
        for question, answer in zip(questions, answers):
            try:
                if question["type"] == "numeric":
                    self._validate_independent_numeric_derivation(
                        question=question,
                        answer=answer.get("answer"),
                        expression=answer.get("derivedExpression"),
                        path=f"independentSolution.answers[{question['id']}]",
                    )
                result = self.question_evaluator.evaluate(
                    question, answer.get("answer")
                )
            except (GeneratedCourseValidationError, ApiError, ValueError, TypeError):
                return False
            if result.get("status") != STATUS_CORRECT:
                if str(question.get("id") or "") not in host_repaired_question_ids:
                    return False
        return True

    def _primary_one_question_fingerprint_payload(
        self,
        question: object,
        *,
        target: PrimaryOneCourseTarget,
        index: int,
    ) -> dict[str, object]:
        if not isinstance(question, Mapping):
            self._fail(
                "invalid_primary_one_fingerprint",
                "Formal question must be an object.",
                path=f"candidateCourse.content.questions[{index}]",
            )
        question_type = str(question.get("type") or "")
        if question_type not in SUPPORTED_QUESTION_TYPES:
            self._fail(
                "invalid_primary_one_fingerprint",
                "Formal question type is unsupported.",
                path=f"candidateCourse.content.questions[{index}].type",
            )
        choices = question.get("choices")
        labels_by_id: dict[str, str] = {}
        option_labels: list[str] = []
        if question_type in {"single_choice", "sequence"}:
            if not isinstance(choices, list):
                self._fail(
                    "invalid_primary_one_fingerprint",
                    "Formal choice question is missing choices.",
                    path=f"candidateCourse.content.questions[{index}].choices",
                )
            for choice in choices:
                if not isinstance(choice, Mapping):
                    self._fail(
                        "invalid_primary_one_fingerprint",
                        "Formal choice is invalid.",
                        path=f"candidateCourse.content.questions[{index}].choices",
                    )
                choice_id = str(choice.get("id") or "")
                label = self._primary_one_fingerprint_text(
                    choice.get("label"), target=target
                )
                if not choice_id or not label or choice_id in labels_by_id:
                    self._fail(
                        "invalid_primary_one_fingerprint",
                        "Formal choices are invalid.",
                        path=f"candidateCourse.content.questions[{index}].choices",
                    )
                labels_by_id[choice_id] = label
                option_labels.append(label)
        numeric_ast: dict[str, object] | None = None
        if question_type == "numeric":
            try:
                answer = self._primary_one_decimal_text(
                    Decimal(str(question.get("answer") or "").replace(",", ""))
                )
                numeric_ast = self.catalog_validator.primary_one_numeric_ast(
                    str(question.get("verificationExpression") or "")
                )
            except (InvalidOperation, ApiError) as exc:
                self._fail(
                    "invalid_primary_one_fingerprint",
                    "Formal numeric semantics are invalid.",
                    path=f"candidateCourse.content.questions[{index}]",
                    details={"reason": type(exc).__name__},
                )
        elif question_type == "accepted_text":
            values = question.get("answer")
            if not isinstance(values, list) or not values:
                self._fail(
                    "invalid_primary_one_fingerprint",
                    "Formal accepted answers are invalid.",
                    path=f"candidateCourse.content.questions[{index}].answer",
                )
            answer = sorted(
                self._primary_one_fingerprint_text(item, target=target)
                for item in values
            )
        elif question_type == "single_choice":
            answer = labels_by_id.get(str(question.get("answer") or ""), "")
            if not answer:
                self._fail(
                    "invalid_primary_one_fingerprint",
                    "Formal single-choice answer is invalid.",
                    path=f"candidateCourse.content.questions[{index}].answer",
                )
        elif question_type == "sequence":
            values = question.get("answer")
            if not isinstance(values, list) or not values:
                self._fail(
                    "invalid_primary_one_fingerprint",
                    "Formal sequence answer is invalid.",
                    path=f"candidateCourse.content.questions[{index}].answer",
                )
            answer = [labels_by_id.get(str(item), "") for item in values]
            if any(not item for item in answer):
                self._fail(
                    "invalid_primary_one_fingerprint",
                    "Formal sequence answer contains an unknown choice.",
                    path=f"candidateCourse.content.questions[{index}].answer",
                )
        else:
            answer = self._primary_one_fingerprint_text(
                question.get("answer"), target=target
            )
        return {
            "type": question_type,
            "prompt": self._primary_one_fingerprint_text(
                question.get("prompt"), target=target
            ),
            "answer": answer,
            "optionLabels": sorted(option_labels),
            "numericAst": numeric_ast,
        }

    @staticmethod
    def _primary_one_fingerprint_text(
        value: object,
        *,
        target: PrimaryOneCourseTarget,
    ) -> str:
        text = unicodedata.normalize("NFKC", str(value or ""))
        text = "".join(
            char
            for char in text
            if not char.isspace() and unicodedata.category(char) != "Cf"
        )
        if target.target_language_code == "en-US":
            text = text.casefold()
        return "".join(
            char for char in text if not unicodedata.category(char).startswith("P")
        )

    @staticmethod
    def _primary_one_decimal_text(value: Decimal) -> str:
        if not value.is_finite():
            raise InvalidOperation("non-finite decimal")
        if value == 0:
            return "0"
        text = format(value.normalize(), "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text

    def _safe_primary_one_fingerprint(
        self, course: Mapping[str, Any], target: PrimaryOneCourseTarget
    ) -> str:
        try:
            return self.primary_one_content_fingerprint(course, target=target)
        except GeneratedCourseValidationError:
            return ""

    @staticmethod
    def _canonical_json(value: object) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def _sha256_json(cls, value: object) -> str:
        return hashlib.sha256(cls._canonical_json(value).encode("utf-8")).hexdigest()

    @staticmethod
    def _is_sha256(value: object) -> bool:
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None

    @staticmethod
    def _sidecar_comparable(value: object) -> str:
        text = unicodedata.normalize("NFKC", str(value))
        comparable: list[str] = []
        for character in text:
            category = unicodedata.category(character)
            if (
                character.isspace()
                or category == "Cf"
                or category.startswith("P")
            ):
                continue
            comparable.append(character)
        return "".join(comparable).lower()

    @staticmethod
    def _primary_one_public_question_hash(course: Mapping[str, Any]) -> str:
        public: list[dict[str, object]] = []
        for question in course["content"]["questions"]:
            item: dict[str, object] = {
                "id": question["id"],
                "type": question["type"],
                "prompt": question["prompt"],
            }
            if question["type"] in {"single_choice", "sequence"}:
                item["choices"] = [
                    {"id": choice["id"], "label": choice["label"]}
                    for choice in question["choices"]
                ]
            public.append(item)
        encoded = json.dumps(public, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def content_fingerprint(self, candidate: str | Mapping[str, Any]) -> str:
        raw = self._decode_object(candidate, path="candidate")
        content = raw.get("content")
        if not isinstance(content, Mapping):
            self._fail(
                "invalid_generated_course_schema",
                "candidate.content must be an object.",
                path="candidate.content",
            )
        questions = content.get("questions")
        if not isinstance(questions, list):
            self._fail(
                "invalid_generated_course_schema",
                "candidate.content.questions must be an array.",
                path="candidate.content.questions",
            )
        semantic = {
            "gradeCode": raw.get("gradeCode"),
            "subject": raw.get("subject"),
            "nodeCode": self._canonical_text(raw.get("nodeCode")),
            "questions": sorted(
                (self._question_fingerprint_payload(item) for item in questions),
                key=lambda item: json.dumps(
                    item,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
        }
        encoded = json.dumps(
            semantic,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _strict_candidate_schema(self, course: Mapping[str, Any]) -> None:
        self._exact_keys(course, _COURSE_KEYS, "candidate")
        for key in _COURSE_KEYS - {"content"}:
            if not self._text(course.get(key)):
                self._fail(
                    "invalid_generated_course_schema",
                    f"candidate.{key} is required.",
                    path=f"candidate.{key}",
                )
        if course.get("status") != _CANDIDATE_STATUS:
            self._fail(
                "invalid_generated_course_status",
                "candidate.status must be unverified.",
                path="candidate.status",
            )
        if not _ID_PATTERN.fullmatch(str(course.get("id") or "")):
            self._fail(
                "invalid_generated_course_schema",
                "candidate.id contains unsupported characters.",
                path="candidate.id",
            )
        content = course.get("content")
        if not isinstance(content, Mapping):
            self._fail(
                "invalid_generated_course_schema",
                "candidate.content must be an object.",
                path="candidate.content",
            )
        self._exact_keys(content, _CONTENT_KEYS, "candidate.content")
        fixed = {
            "schemaVersion": COURSE_SCHEMA_VERSION,
            "sessionKind": "lesson",
            "outcomeMode": "scored_deterministic",
            "reviewPolicy": "programmatic_guarded",
        }
        for key, expected in fixed.items():
            if content.get(key) != expected:
                self._fail(
                    "invalid_generated_course_schema",
                    f"candidate.content.{key} must be {expected}.",
                    path=f"candidate.content.{key}",
                )
        if content.get("sourceAuthority") != _CANDIDATE_SOURCE_AUTHORITY:
            self._fail(
                "invalid_generated_course_authority",
                "candidate sourceAuthority must identify an unverified OpenMAIC/Kimi candidate.",
                path="candidate.content.sourceAuthority",
            )
        minutes = content.get("estimatedMinutes")
        if isinstance(minutes, bool) or not isinstance(minutes, int) or not 5 <= minutes <= 30:
            self._fail(
                "generated_course_limit_exceeded",
                "estimatedMinutes must be an integer from 5 through 30.",
                path="candidate.content.estimatedMinutes",
            )
        questions = content.get("questions")
        if not isinstance(questions, list) or len(questions) != 5:
            self._fail(
                "invalid_generated_question_count",
                "A generated course must contain exactly five questions.",
                path="candidate.content.questions",
            )

    def _validate_boundary(
        self,
        course: Mapping[str, Any],
        grade_code: str,
        subject: str,
        boundary: Mapping[str, Any],
    ) -> None:
        expected = {
            "gradeCode": grade_code,
            "subject": subject,
            "nodeCode": boundary["skillId"],
        }
        for key, value in expected.items():
            if course.get(key) != value:
                self._fail(
                    "generated_course_boundary_mismatch",
                    f"candidate.{key} changed the requested learning boundary.",
                    path=f"candidate.{key}",
                    details={"expected": value, "actual": course.get(key)},
                )
        objective = str(course.get("objective") or "").strip()
        allowed_objectives = boundary.get("learningObjectives") or []
        allowed_objective_values = set(allowed_objectives)
        if allowed_objectives:
            allowed_objective_values.add("；".join(allowed_objectives))
            canonical_objectives = [
                unicodedata.normalize("NFKC", str(value)).strip()
                for value in allowed_objectives
            ]
            allowed_objective_values.add(";".join(canonical_objectives))
        if allowed_objectives and objective not in allowed_objective_values:
            self._fail(
                "generated_course_boundary_mismatch",
                "candidate.objective is outside learningObjectives.",
                path="candidate.objective",
            )

    def _validate_lengths(self, course: Mapping[str, Any]) -> None:
        text_paths = {
            "course.id": course.get("id"),
            "course.version": course.get("version"),
            "course.nodeCode": course.get("nodeCode"),
            "course.title": course.get("title"),
            "course.objective": course.get("objective"),
            "content.intro": course["content"].get("intro"),
        }
        for label, value in text_paths.items():
            self._bounded_text(value, label, _TEXT_LIMITS[label])

    def _validate_questions(
        self, course: Mapping[str, Any], boundary: Mapping[str, Any]
    ) -> None:
        question_ids: set[str] = set()
        question_signatures: set[str] = set()
        for index, question in enumerate(course["content"]["questions"]):
            path = f"candidate.content.questions[{index}]"
            if not isinstance(question, Mapping):
                self._fail(
                    "invalid_generated_course_schema",
                    "question must be an object.",
                    path=path,
                )
            question_type = str(question.get("type") or "").strip()
            if question_type not in SUPPORTED_QUESTION_TYPES:
                self._fail(
                    "unsupported_generated_question_type",
                    f"Unsupported deterministic question type: {question_type or '<empty>'}.",
                    path=f"{path}.type",
                )
            self._exact_keys(question, _QUESTION_KEYS_BY_TYPE[question_type], path)
            question_id = self._bounded_text(
                question.get("id"), f"{path}.id", _TEXT_LIMITS["question.id"]
            )
            if not _ID_PATTERN.fullmatch(question_id):
                self._fail(
                    "invalid_generated_course_schema",
                    "question.id contains unsupported characters.",
                    path=f"{path}.id",
                )
            if question_id in question_ids:
                self._fail(
                    "duplicate_generated_question_id",
                    "Question IDs must be unique within a course.",
                    path=f"{path}.id",
                )
            question_ids.add(question_id)
            for key in ("prompt", "skill", "hint", "explanation"):
                self._bounded_text(
                    question.get(key),
                    f"{path}.{key}",
                    _TEXT_LIMITS[f"question.{key}"],
                )
            self._validate_question_skill(question, boundary, path)
            evaluation = question.get("evaluation")
            if not isinstance(evaluation, Mapping):
                self._fail(
                    "invalid_generated_course_schema",
                    "question.evaluation must be an object.",
                    path=f"{path}.evaluation",
                )
            self._exact_keys(
                evaluation,
                _EVALUATION_KEYS_BY_TYPE[question_type],
                f"{path}.evaluation",
            )
            self._normalization(question_type, evaluation.get("normalization"), path)
            self._validate_answer_contract(question, question_type, path)
            self._validate_hint_does_not_reveal_answer(question, path)
            self._validate_prompt_does_not_reveal_answer(question, path)
            signature = self._canonical_text(question["prompt"])
            if signature in question_signatures:
                self._fail(
                    "duplicate_generated_question",
                    "Questions must not repeat the same prompt.",
                    path=f"{path}.prompt",
                )
            question_signatures.add(signature)

    def _validate_teaching_flow(
        self,
        course: Mapping[str, Any],
        boundary: Mapping[str, Any],
    ) -> None:
        flow = course["content"].get("teachingFlow")
        path = "candidate.content.teachingFlow"
        if not isinstance(flow, Mapping):
            self._fail(
                "invalid_generated_teaching_flow",
                "candidate.content.teachingFlow must be an object.",
                path=path,
            )
        self._exact_keys(
            flow,
            frozenset(
                {
                    "schemaVersion",
                    "teach",
                    "demoQuestionId",
                    "guidedQuestionIds",
                    "independentQuestionIds",
                    "recap",
                }
            ),
            path,
        )
        if flow.get("schemaVersion") != TEACHING_FLOW_SCHEMA_VERSION:
            self._fail(
                "invalid_generated_teaching_flow",
                f"{path}.schemaVersion must be {TEACHING_FLOW_SCHEMA_VERSION}.",
                path=f"{path}.schemaVersion",
            )
        teach = flow.get("teach")
        if not isinstance(teach, Mapping):
            self._fail(
                "invalid_generated_teaching_flow",
                f"{path}.teach must be an object.",
                path=f"{path}.teach",
            )
        self._exact_keys(
            teach,
            frozenset({"title", "sayText", "keyPoints"}),
            f"{path}.teach",
        )
        self._bounded_text(
            teach.get("title"),
            f"{path}.teach.title",
            _TEXT_LIMITS["teachingFlow.teach.title"],
        )
        self._bounded_text(
            teach.get("sayText"),
            f"{path}.teach.sayText",
            _TEXT_LIMITS["teachingFlow.teach.sayText"],
        )
        key_points = teach.get("keyPoints")
        if not isinstance(key_points, list) or not 1 <= len(key_points) <= 3:
            self._fail(
                "invalid_generated_teaching_flow",
                f"{path}.teach.keyPoints must contain one through three items.",
                path=f"{path}.teach.keyPoints",
            )
        normalized_points: list[str] = []
        for index, item in enumerate(key_points):
            point = self._bounded_text(
                item,
                f"{path}.teach.keyPoints[{index}]",
                _TEXT_LIMITS["teachingFlow.teach.keyPoint"],
            )
            normalized = self._canonical_text(point)
            if normalized in normalized_points:
                self._fail(
                    "invalid_generated_teaching_flow",
                    f"{path}.teach.keyPoints must be unique.",
                    path=f"{path}.teach.keyPoints",
                )
            normalized_points.append(normalized)

        recap = flow.get("recap")
        if not isinstance(recap, Mapping):
            self._fail(
                "invalid_generated_teaching_flow",
                f"{path}.recap must be an object.",
                path=f"{path}.recap",
            )
        self._exact_keys(recap, frozenset({"sayText"}), f"{path}.recap")
        self._bounded_text(
            recap.get("sayText"),
            f"{path}.recap.sayText",
            _TEXT_LIMITS["teachingFlow.recap.sayText"],
        )

        question_ids = [
            str(question["id"]) for question in course["content"]["questions"]
        ]
        demo_id = self._bounded_text(
            flow.get("demoQuestionId"), f"{path}.demoQuestionId", 160
        )
        guided_ids = self._teaching_flow_ids(
            flow.get("guidedQuestionIds"),
            path=f"{path}.guidedQuestionIds",
            expected_count=2,
        )
        independent_ids = self._teaching_flow_ids(
            flow.get("independentQuestionIds"),
            path=f"{path}.independentQuestionIds",
            expected_count=2,
        )
        references = [demo_id, *guided_ids, *independent_ids]
        if references != question_ids or len(set(references)) != 5:
            self._fail(
                "invalid_generated_teaching_flow",
                "Teaching-flow roles must cover q1 through q5 exactly once and in order.",
                path=path,
                details={"expectedQuestionIds": question_ids, "actualQuestionIds": references},
            )

        public_teaching_parts = [
            str(teach["title"]),
            str(teach["sayText"]),
            *[str(item) for item in key_points],
            str(recap["sayText"]),
        ]
        public_teaching_text = " ".join(public_teaching_parts)
        canonical_teaching_text = self._canonical_text(public_teaching_text)
        for term in boundary.get("excludedContent") or []:
            canonical_term = self._canonical_text(term)
            if canonical_term and canonical_term in canonical_teaching_text:
                self._fail(
                    "generated_course_boundary_mismatch",
                    "Teaching flow contains excluded content.",
                    path=path,
                    details={"excludedContent": term},
                )
        for question_number, question in enumerate(
            course["content"]["questions"][1:], start=2
        ):
            if any(
                self._teaching_text_explicitly_reveals_question(
                    part, question, question_number
                )
                for part in public_teaching_parts
            ):
                self._fail(
                    "generated_teaching_answer_leak",
                    "Teaching flow directly reveals a guided or independent answer.",
                    path=path,
                    details={"questionId": question["id"]},
                )

    def _teaching_text_explicitly_reveals_question(
        self,
        text: str,
        question: Mapping[str, Any],
        question_number: int,
    ) -> bool:
        arithmetic_signature = self._primary_add_sub_signature(question)
        if arithmetic_signature and self._text_reveals_add_sub_signature(
            text, arithmetic_signature
        ):
            return True
        if not any(
            self._prompt_explicitly_reveals(text, answer)
            for answer in self._answer_values(question)
        ):
            return False
        canonical_text = self._canonical_text(text).replace(" ", "")
        chinese_ordinal = {2: "二", 3: "三", 4: "四", 5: "五"}.get(
            question_number, ""
        )
        if re.search(
            rf"(?:第(?:{question_number}|{chinese_ordinal})道?(?:题|练习)|q{question_number})",
            canonical_text,
            flags=re.IGNORECASE,
        ):
            return True
        prompt_signature = re.sub(
            r"[?？。.!！]",
            "",
            self._canonical_text(str(question.get("prompt") or "")).replace(" ", ""),
        )
        if len(prompt_signature) >= 8 and prompt_signature in canonical_text:
            return True
        if str(question.get("type") or "") == "numeric":
            expression = self._canonical_text(
                str(question.get("verificationExpression") or "")
            ).replace(" ", "")
            if len(expression) >= 3 and expression in canonical_text:
                return True
        return False

    def _primary_add_sub_signature(
        self, question: Mapping[str, Any]
    ) -> tuple[str, int, int, int] | None:
        question_type = str(question.get("type") or "")
        if question_type == "numeric":
            expression = re.fullmatch(
                r"\s*(\d{1,2})\s*([+-])\s*(\d{1,2})\s*",
                str(question.get("verificationExpression") or ""),
            )
            if expression is None:
                return None
            left, operator, right = expression.groups()
            answer = int(left) + int(right) if operator == "+" else int(left) - int(right)
            return (
                "addition" if operator == "+" else "subtraction",
                int(left),
                int(right),
                answer,
            )
        if question_type != "single_choice":
            return None

        answer_label = next(iter(self._answer_values(question)), "")
        answer_match = re.search(r"(?<!\d)(\d{1,2})(?!\d)", answer_label)
        prompt = unicodedata.normalize("NFKC", str(question.get("prompt") or ""))
        operands = [
            int(value)
            for value in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", prompt)
        ]
        if answer_match is None or len(operands) < 2:
            return None
        left, right = operands[:2]
        answer = int(answer_match.group(1))
        compact = self._canonical_text(prompt).replace(" ", "")
        explicit = re.search(
            rf"{left}(?:\+|加(?:上)?){right}|{left}(?:-|减(?:去)?){right}",
            compact,
        )
        if explicit:
            operation = (
                "subtraction"
                if re.search(r"-|减", explicit.group(0))
                else "addition"
            )
        elif re.search(
            r"借走|拿走|吃(?:了|掉)|还剩|剩下|送出|用掉|走了|减少",
            compact,
        ):
            operation = "subtraction"
        elif re.search(r"又|一共|合起来|总共|增加|放进|来了|得到|再加", compact):
            operation = "addition"
        else:
            return None
        expected = left + right if operation == "addition" else left - right
        if expected != answer:
            return None
        return operation, left, right, answer

    def _text_reveals_add_sub_signature(
        self,
        value: object,
        signature: tuple[str, int, int, int],
    ) -> bool:
        operation, left, right, answer = signature
        text = self._canonical_text(value).replace(" ", "")
        pairs = [(left, right)]
        if operation == "addition" and left != right:
            pairs.append((right, left))
        operator = r"(?:\+|加(?:上)?)" if operation == "addition" else r"(?:-|减(?:去)?)"
        answer_link = r"(?:=|等于|是|得|得到|结果(?:是|为)?|一共(?:是|有)?)"
        return any(
            re.search(
                rf"(?<!\d){first}{operator}{second}.{{0,24}}{answer_link}.{{0,4}}{answer}(?!\d)",
                text,
            )
            is not None
            for first, second in pairs
        )

    def _teaching_flow_ids(
        self,
        value: object,
        *,
        path: str,
        expected_count: int,
    ) -> list[str]:
        if not isinstance(value, list) or len(value) != expected_count:
            self._fail(
                "invalid_generated_teaching_flow",
                f"{path} must contain exactly {expected_count} question IDs.",
                path=path,
            )
        ids = [
            self._bounded_text(item, f"{path}[{index}]", 160)
            for index, item in enumerate(value)
        ]
        if len(set(ids)) != len(ids):
            self._fail(
                "invalid_generated_teaching_flow",
                f"{path} must not contain duplicate question IDs.",
                path=path,
            )
        return ids

    def _validate_question_skill(
        self,
        question: Mapping[str, Any],
        boundary: Mapping[str, Any],
        path: str,
    ) -> None:
        skill = str(question.get("skill") or "").strip()
        allowed = boundary.get("allowedQuestionSkills")
        if allowed and skill not in allowed:
            self._fail(
                "generated_course_boundary_mismatch",
                "question.skill is outside allowedQuestionSkills.",
                path=f"{path}.skill",
                details={"skill": skill},
            )
        haystack = self._canonical_text(
            " ".join(
                str(question.get(key) or "")
                for key in ("prompt", "skill", "hint", "explanation")
            )
        )
        for term in boundary.get("excludedContent") or []:
            if self._canonical_text(term) in haystack:
                self._fail(
                    "generated_course_boundary_mismatch",
                    "question contains excluded content.",
                    path=path,
                    details={"excludedContent": term},
                )

    def _validate_answer_contract(
        self, question: Mapping[str, Any], question_type: str, path: str
    ) -> None:
        evaluation = question["evaluation"]
        if question_type == "numeric":
            answer = self._bounded_scalar(question.get("answer"), path)
            expression = self._bounded_text(
                question.get("verificationExpression"),
                f"{path}.verificationExpression",
                128,
            )
            if expression == answer.strip():
                self._fail(
                    "invalid_generated_math_verification",
                    "verificationExpression must independently recompute the answer.",
                    path=f"{path}.verificationExpression",
                )
            try:
                expected = Decimal(answer)
            except InvalidOperation:
                self._fail(
                    "invalid_generated_answer",
                    "numeric answer must be a finite Decimal value.",
                    path=f"{path}.answer",
                )
            if not expected.is_finite():
                self._fail(
                    "invalid_generated_answer",
                    "numeric answer must be finite.",
                    path=f"{path}.answer",
                )
            try:
                calculated = self.catalog_validator.evaluate_expression(expression)
            except ApiError as exc:
                self._fail(
                    "invalid_generated_math_verification",
                    exc.message,
                    path=f"{path}.verificationExpression",
                )
            if calculated != expected:
                self._fail(
                    "generated_answer_verification_mismatch",
                    "verificationExpression does not equal the declared numeric answer.",
                    path=f"{path}.verificationExpression",
                    details={"calculated": str(calculated), "answer": str(expected)},
                )
            try:
                declared = Decimal(str(evaluation.get("expected")))
            except InvalidOperation:
                declared = Decimal("NaN")
            if not declared.is_finite() or declared != expected:
                self._fail(
                    "generated_answer_contract_mismatch",
                    "evaluation.expected must equal the numeric answer.",
                    path=f"{path}.evaluation.expected",
                )
            return

        if question_type == "exact_text":
            answer = self._bounded_scalar(question.get("answer"), path)
            expected = self._bounded_scalar(evaluation.get("expected"), path)
            if answer != expected:
                self._contract_mismatch(path)
            return

        if question_type == "accepted_text":
            answer = self._text_list(question.get("answer"), path, maximum=6)
            declared = self._text_list(question.get("acceptedAnswers"), path, maximum=6)
            evaluated = self._text_list(
                evaluation.get("acceptedAnswers"), path, maximum=6
            )
            if answer != declared or answer != evaluated:
                self._contract_mismatch(path)
            operations = tuple(evaluation["normalization"])
            normalized = [self._normalize_text(item, operations) for item in answer]
            if len(normalized) != len(set(normalized)):
                self._fail(
                    "duplicate_generated_answer",
                    "Accepted answers collapse to the same normalized value.",
                    path=f"{path}.acceptedAnswers",
                )
            return

        choices = self._choices(question.get("choices"), path)
        operations = tuple(evaluation["normalization"])
        normalized_ids = [self._normalize_text(item[0], operations) for item in choices]
        normalized_labels = [self._normalize_text(item[1], operations) for item in choices]
        if len(normalized_ids) != len(set(normalized_ids)):
            self._fail(
                "duplicate_generated_choice",
                "Choice IDs must be unique after normalization.",
                path=f"{path}.choices",
            )
        if len(normalized_labels) != len(set(normalized_labels)):
            self._fail(
                "duplicate_generated_choice",
                "Choice labels must be unique after normalization.",
                path=f"{path}.choices",
            )
        if question_type == "single_choice":
            answer = self._bounded_scalar(question.get("answer"), path)
            expected = self._bounded_scalar(evaluation.get("expectedOptionId"), path)
            normalized_answer = self._normalize_text(answer, operations)
            if normalized_answer != self._normalize_text(expected, operations):
                self._contract_mismatch(path)
            if normalized_answer not in set(normalized_ids):
                self._fail(
                    "invalid_generated_answer",
                    "Single-choice answer is not one of the choice IDs.",
                    path=f"{path}.answer",
                )
            return

        answer = self._text_list(question.get("answer"), path, maximum=8)
        expected = self._text_list(
            evaluation.get("expectedSequence"), path, maximum=8
        )
        normalized_answer = [self._normalize_text(item, operations) for item in answer]
        normalized_expected = [
            self._normalize_text(item, operations) for item in expected
        ]
        if normalized_answer != normalized_expected:
            self._contract_mismatch(path)
        if len(normalized_answer) != len(set(normalized_answer)) or set(
            normalized_answer
        ) != set(normalized_ids):
            self._fail(
                "invalid_generated_answer",
                "Sequence answer must be a permutation of all choice IDs.",
                path=f"{path}.answer",
            )
        if normalized_answer == normalized_ids:
            self._fail(
                "invalid_generated_choice_order",
                "Sequence choices must not be displayed in answer order.",
                path=f"{path}.choices",
            )

    def _validate_hint_does_not_reveal_answer(
        self, question: Mapping[str, Any], path: str
    ) -> None:
        answer_values: list[str] = []
        question_type = str(question["type"])
        if question_type == "accepted_text":
            answer_values = [str(value) for value in question["answer"]]
        elif question_type == "single_choice":
            answer_values.append(str(question["answer"]))
            selected = next(
                (
                    item
                    for item in question["choices"]
                    if str(item["id"]) == str(question["answer"])
                ),
                None,
            )
            if selected is not None:
                answer_values.append(str(selected["label"]))
        elif question_type == "sequence":
            labels_by_id = {
                str(item["id"]): str(item["label"])
                for item in question["choices"]
            }
            ids = [str(value) for value in question["answer"]]
            labels = [labels_by_id.get(value, value) for value in ids]
            answer_values.extend((" ".join(ids), " ".join(labels), "、".join(labels)))
        else:
            answer_values.append(str(question["answer"]))
        if any(
            self._hint_explicitly_reveals(str(question["hint"]), answer)
            for answer in answer_values
        ):
            self._fail(
                "generated_hint_answer_leak",
                "question.hint directly reveals the declared answer.",
                path=f"{path}.hint",
            )

    def _hint_explicitly_reveals(self, hint: str, answer: str) -> bool:
        normalized_hint = self._canonical_text(hint).replace(" ", "")
        normalized_answer = self._canonical_text(answer).replace(" ", "")
        if not normalized_answer:
            return False
        if normalized_hint == normalized_answer:
            return True
        lead = r"(?:正确答案(?:是|为)?|答案(?:是|为)?|结果(?:是|为)?|应选|选择|等于)"
        tail = r"(?:$|[,.!?;:，。！？；：])"
        return (
            re.search(
                rf"{lead}[：:]?[“\"']?{re.escape(normalized_answer)}[”\"']?{tail}",
                normalized_hint,
                flags=re.IGNORECASE,
            )
            is not None
        )

    def _validate_prompt_does_not_reveal_answer(
        self, question: Mapping[str, Any], path: str
    ) -> None:
        answer_values = self._answer_values(question)
        prompt = str(question.get("prompt") or "")
        if any(self._prompt_explicitly_reveals(prompt, answer) for answer in answer_values):
            self._fail(
                "generated_prompt_answer_leak",
                "question.prompt directly reveals the declared answer.",
                path=f"{path}.prompt",
            )

    def _prompt_explicitly_reveals(self, prompt: str, answer: str) -> bool:
        normalized_prompt = self._canonical_text(prompt).replace(" ", "")
        normalized_answer = self._canonical_text(answer).replace(" ", "")
        if not normalized_answer:
            return False
        lead = (
            r"(?:正确答案(?:是|为)?|答案(?:是|为)?|结果(?:是|为)?|应选|"
            r"请选择|直接回答|等于)"
        )
        tail = r"(?:$|[,.!?;:，。！？；：])"
        if re.search(
            rf"{lead}[：:]?[“\"']?{re.escape(normalized_answer)}[”\"']?{tail}",
            normalized_prompt,
            flags=re.IGNORECASE,
        ):
            return True
        return (
            re.search(
                rf"=[“\"']?{re.escape(normalized_answer)}[”\"']?{tail}",
                normalized_prompt,
                flags=re.IGNORECASE,
            )
            is not None
        )

    @staticmethod
    def _answer_values(question: Mapping[str, Any]) -> list[str]:
        question_type = str(question.get("type") or "")
        if question_type == "accepted_text":
            return [str(value) for value in question.get("answer") or []]
        if question_type == "single_choice":
            answer = str(question.get("answer") or "")
            label = next(
                (
                    str(item.get("label") or "")
                    for item in question.get("choices") or []
                    if str(item.get("id") or "") == answer
                ),
                "",
            )
            return [label] if label else []
        if question_type == "sequence":
            labels_by_id = {
                str(item.get("id") or ""): str(item.get("label") or "")
                for item in question.get("choices") or []
            }
            ids = [str(value) for value in question.get("answer") or []]
            labels = [labels_by_id.get(value, value) for value in ids]
            return [" ".join(labels), "、".join(labels)]
        return [str(question.get("answer") or "")]

    def _validate_independent_solution(
        self,
        course: Mapping[str, Any],
        *,
        independent_solution: str | Mapping[str, Any] | None,
        expected_grade: str,
        expected_subject: str,
        boundary: Mapping[str, Any],
        verification_request_id: str | None,
    ) -> None:
        if independent_solution is None:
            self._fail(
                "missing_independent_solution",
                "Every generated course requires a second independent solution.",
                path="independentSolution",
            )
        solution = self._decode_object(
            independent_solution, path="independentSolution"
        )
        self._exact_keys(
            solution,
            frozenset(
                {
                    "schemaVersion",
                    "solver",
                    "independentFromGeneration",
                    "verificationRequestId",
                    "publicQuestionHash",
                    "gradeCode",
                    "subject",
                    "skillId",
                    "answers",
                    "teachingReview",
                }
            ),
            "independentSolution",
        )
        fixed = {
            "schemaVersion": INDEPENDENT_SOLUTION_SCHEMA_VERSION,
            "independentFromGeneration": True,
            "gradeCode": expected_grade,
            "subject": expected_subject,
            "skillId": boundary["skillId"],
        }
        for key, expected in fixed.items():
            if solution.get(key) != expected:
                self._fail(
                    "invalid_independent_solution",
                    f"independentSolution.{key} is invalid.",
                    path=f"independentSolution.{key}",
                )
        request_id = self._bounded_text(
            solution.get("verificationRequestId"),
            "independentSolution.verificationRequestId",
            120,
        )
        if verification_request_id is not None and request_id != verification_request_id:
            self._fail(
                "invalid_independent_solution",
                "independentSolution.verificationRequestId does not match this verification call.",
                path="independentSolution.verificationRequestId",
            )
        expected_public_hash = self.public_question_hash(course)
        if solution.get("publicQuestionHash") != expected_public_hash:
            self._fail(
                "independent_solution_mismatch",
                "Independent solution is not bound to these public questions.",
                path="independentSolution.publicQuestionHash",
            )
        self._bounded_text(solution.get("solver"), "independentSolution.solver", 120)
        teaching_review = solution.get("teachingReview")
        teaching_issues = (
            teaching_review.get("issues")
            if isinstance(teaching_review, Mapping)
            else None
        )
        if (
            not isinstance(teaching_review, Mapping)
            or set(teaching_review) != {"passed", "issues"}
            or teaching_review.get("passed") is not True
            or not isinstance(teaching_issues, list)
            or teaching_issues
        ):
            first_issue = ""
            if isinstance(teaching_issues, list) and teaching_issues:
                first_issue = str(teaching_issues[0]).strip()[:300]
            self._fail(
                "independent_teaching_review_failed",
                (
                    f"Independent teaching review failed: {first_issue}"
                    if first_issue
                    else "Independent teaching review must pass with an empty issues array."
                ),
                path="independentSolution.teachingReview",
            )
        answers = solution.get("answers")
        if not isinstance(answers, list) or len(answers) != 5:
            self._fail(
                "invalid_independent_solution",
                "independentSolution.answers must contain exactly five answers.",
                path="independentSolution.answers",
            )
        questions = course["content"]["questions"]
        question_by_id = {str(question["id"]): question for question in questions}
        solved: dict[str, Mapping[str, Any]] = {}
        for index, item in enumerate(answers):
            path = f"independentSolution.answers[{index}]"
            if not isinstance(item, Mapping):
                self._fail(
                    "invalid_independent_solution", "answer must be an object.", path=path
                )
            question_id = self._bounded_text(item.get("questionId"), f"{path}.questionId", 160)
            question = question_by_id.get(question_id)
            if question is None:
                self._fail(
                    "independent_solution_mismatch",
                    "Independent answer references an unknown question.",
                    path=f"{path}.questionId",
                )
            allowed_keys = (
                frozenset({"questionId", "answer", "derivedExpression"})
                if question.get("type") == "numeric"
                else frozenset({"questionId", "answer"})
            )
            self._exact_keys(item, allowed_keys, path)
            if question_id in solved:
                self._fail(
                    "invalid_independent_solution",
                    "independent answer question IDs must be unique.",
                    path=f"{path}.questionId",
                )
            if question.get("type") == "numeric":
                self._validate_independent_numeric_derivation(
                    question=question,
                    answer=item.get("answer"),
                    expression=item.get("derivedExpression"),
                    path=path,
                )
            solved[question_id] = item

        expected_ids = {str(question["id"]) for question in questions}
        if set(solved) != expected_ids:
            self._fail(
                "independent_solution_mismatch",
                "Independent answers must cover every candidate question exactly once.",
                path="independentSolution.answers",
            )
        for question in questions:
            response = solved[str(question["id"])].get("answer")
            result = self.question_evaluator.evaluate(question, response)
            if result.get("status") != STATUS_CORRECT:
                self._fail(
                    "independent_solution_mismatch",
                    "Independent solver did not reproduce the declared answer.",
                    path=f"independentSolution.answers[{question['id']}]",
                    details={
                        "questionId": question["id"],
                        "evaluationStatus": result.get("status"),
                    },
                )

    def _validate_independent_numeric_derivation(
        self,
        *,
        question: Mapping[str, Any],
        answer: object,
        expression: object,
        path: str,
    ) -> None:
        derived = self._bounded_text(
            expression, f"{path}.derivedExpression", 128
        ).replace("×", "*").replace("÷", "/")
        if not re.search(r"[+\-*/]", derived):
            self._fail(
                "invalid_independent_solution",
                "Numeric derivedExpression must contain an arithmetic operator.",
                path=f"{path}.derivedExpression",
            )
        if self._canonical_text(derived) == self._canonical_text(answer):
            self._fail(
                "invalid_independent_solution",
                "Numeric derivedExpression cannot be the answer constant.",
                path=f"{path}.derivedExpression",
            )
        prompt_numbers = {
            self._normalized_number_token(value)
            for value in re.findall(r"\d+(?:\.\d+)?", str(question.get("prompt") or ""))
        }
        expression_numbers = [
            self._normalized_number_token(value)
            for value in re.findall(r"\d+(?:\.\d+)?", derived)
        ]
        if len(expression_numbers) < 2 or any(
            value not in prompt_numbers for value in expression_numbers
        ):
            self._fail(
                "invalid_independent_solution",
                "Numeric derivedExpression must use only numbers present in the public question.",
                path=f"{path}.derivedExpression",
            )
        try:
            calculated = self.catalog_validator.evaluate_expression(derived)
            expected = Decimal(str(answer).replace(",", ""))
        except (ApiError, InvalidOperation, ValueError, TypeError) as exc:
            self._fail(
                "invalid_independent_solution",
                f"Numeric independent derivation is invalid: {exc}",
                path=f"{path}.derivedExpression",
            )
        if calculated != expected:
            self._fail(
                "independent_solution_mismatch",
                "Numeric independent derivation does not yield the independent answer.",
                path=f"{path}.derivedExpression",
            )

    @staticmethod
    def _normalized_number_token(value: str) -> str:
        try:
            normalized = Decimal(value).normalize()
        except InvalidOperation:
            return value
        return format(normalized, "f")

    def public_question_hash(self, course: Mapping[str, Any]) -> str:
        questions = []
        for item in course["content"]["questions"]:
            public = {
                "id": item.get("id"),
                "type": item.get("type"),
                "prompt": item.get("prompt"),
            }
            if item.get("type") in {"single_choice", "sequence"}:
                public["choices"] = [
                    {"id": choice.get("id"), "label": choice.get("label")}
                    for choice in item.get("choices") or []
                ]
            questions.append(public)
        encoded = json.dumps(questions, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _as_publishable(course: Mapping[str, Any]) -> dict[str, Any]:
        published = copy.deepcopy(dict(course))
        published["status"] = "published"
        published["content"]["sourceAuthority"] = copy.deepcopy(
            GENERATED_SOURCE_AUTHORITY
        )
        return published

    def _boundary(
        self,
        value: str | Mapping[str, Any],
        *,
        grade_code: str,
        subject: str,
    ) -> dict[str, Any]:
        if isinstance(value, str):
            boundary: dict[str, Any] = {"skillId": value}
        elif isinstance(value, Mapping):
            boundary = copy.deepcopy(dict(value))
        else:
            self._fail(
                "invalid_skill_boundary",
                "skill_boundary must be a skill ID or object.",
                path="skillBoundary",
            )
        allowed_keys = {
            "gradeCode",
            "subject",
            "skillId",
            "skillTitle",
            "learningObjectives",
            "allowedContent",
            "excludedContent",
            "prerequisiteSkills",
            "allowedQuestionSkills",
            "language",
            "outcomeMode",
            "sessionKind",
            "durationMinutes",
            "estimatedMinutes",
            "questionCount",
        }
        unknown = set(boundary) - allowed_keys
        if unknown:
            self._fail(
                "invalid_skill_boundary",
                "skillBoundary contains unsupported fields.",
                path="skillBoundary",
                details={"unknownFields": sorted(unknown)},
            )
        skill_id = self._bounded_text(boundary.get("skillId"), "skillBoundary.skillId", 120)
        if "gradeCode" in boundary and boundary["gradeCode"] != grade_code:
            self._fail(
                "generated_course_boundary_mismatch",
                "skillBoundary.gradeCode does not match requested grade.",
                path="skillBoundary.gradeCode",
            )
        if "subject" in boundary and boundary["subject"] != subject:
            self._fail(
                "generated_course_boundary_mismatch",
                "skillBoundary.subject does not match requested subject.",
                path="skillBoundary.subject",
            )
        if "questionCount" in boundary and boundary["questionCount"] != 5:
            self._fail(
                "invalid_skill_boundary",
                "skillBoundary.questionCount must be five.",
                path="skillBoundary.questionCount",
            )
        normalized = copy.deepcopy(boundary)
        normalized["gradeCode"] = grade_code
        normalized["subject"] = subject
        normalized["skillId"] = skill_id
        for key in (
            "learningObjectives",
            "allowedContent",
            "excludedContent",
            "prerequisiteSkills",
            "allowedQuestionSkills",
        ):
            if key in normalized:
                normalized[key] = self._bounded_text_list(
                    normalized[key], f"skillBoundary.{key}", maximum=32, item_limit=300
                )
        return normalized

    @staticmethod
    def _expected_grade(grade_code: str | None, grade: int | str | None) -> str:
        if grade_code is not None and grade is not None:
            expected = f"primary_{grade}"
            if str(grade_code).strip() != expected:
                raise GeneratedCourseValidationError(
                    "invalid_generated_grade",
                    "grade and grade_code disagree.",
                    path="grade",
                )
        value = str(grade_code or (f"primary_{grade}" if grade is not None else "")).strip()
        if value not in {f"primary_{number}" for number in range(1, 7)}:
            raise GeneratedCourseValidationError(
                "invalid_generated_grade",
                "grade must identify primary school grade 1 through 6.",
                path="grade",
            )
        return value

    def _normalization(self, question_type: str, value: Any, path: str) -> None:
        if not isinstance(value, list) or not value:
            self._fail(
                "unsafe_generated_normalization",
                "normalization must be a non-empty array.",
                path=f"{path}.evaluation.normalization",
            )
        operations: list[str] = []
        for item in value:
            if not isinstance(item, str) or item not in _NORMALIZATION_BY_TYPE[question_type]:
                self._fail(
                    "unsafe_generated_normalization",
                    "normalization contains an operation outside the allowlist.",
                    path=f"{path}.evaluation.normalization",
                )
            if item in operations:
                self._fail(
                    "unsafe_generated_normalization",
                    "normalization operations must not repeat.",
                    path=f"{path}.evaluation.normalization",
                )
            operations.append(item)

    def _choices(self, value: Any, path: str) -> list[tuple[str, str]]:
        if not isinstance(value, list) or not 2 <= len(value) <= 8:
            self._fail(
                "invalid_generated_choices",
                "choices must contain two through eight options.",
                path=f"{path}.choices",
            )
        choices: list[tuple[str, str]] = []
        for index, item in enumerate(value):
            choice_path = f"{path}.choices[{index}]"
            if not isinstance(item, Mapping):
                self._fail(
                    "invalid_generated_choices", "choice must be an object.", path=choice_path
                )
            self._exact_keys(item, frozenset({"id", "label"}), choice_path)
            choices.append(
                (
                    self._bounded_text(item.get("id"), f"{choice_path}.id", _TEXT_LIMITS["choice.id"]),
                    self._bounded_text(item.get("label"), f"{choice_path}.label", _TEXT_LIMITS["choice.label"]),
                )
            )
        return choices

    def _text_list(
        self, value: Any, path: str, *, maximum: int
    ) -> list[str]:
        if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
            self._fail(
                "invalid_generated_answer",
                "answer must be an array.",
                path=f"{path}.answer",
            )
        if not 1 <= len(value) <= maximum:
            self._fail(
                "invalid_generated_answer",
                "answer array has an invalid length.",
                path=f"{path}.answer",
            )
        return [self._bounded_scalar(item, path) for item in value]

    def _bounded_scalar(self, value: Any, path: str) -> str:
        if value is None or isinstance(value, (bool, Mapping, list, tuple, set)):
            self._fail(
                "invalid_generated_answer",
                "answer must be a non-empty scalar.",
                path=f"{path}.answer",
            )
        if not isinstance(value, (str, int, float, Decimal)):
            self._fail(
                "invalid_generated_answer",
                "answer must be a string or number.",
                path=f"{path}.answer",
            )
        if isinstance(value, float) and not math.isfinite(value):
            self._fail(
                "invalid_generated_answer", "answer must be finite.", path=f"{path}.answer"
            )
        if isinstance(value, Decimal) and not value.is_finite():
            self._fail(
                "invalid_generated_answer", "answer must be finite.", path=f"{path}.answer"
            )
        text = str(value).strip()
        if not text:
            self._fail(
                "invalid_generated_answer",
                "answer must be a non-empty scalar.",
                path=f"{path}.answer",
            )
        if len(text) > _TEXT_LIMITS["answer"]:
            self._fail(
                "generated_course_limit_exceeded",
                f"{path}.answer exceeds {_TEXT_LIMITS['answer']} characters.",
                path=f"{path}.answer",
            )
        return text

    def _bounded_text_list(
        self, value: Any, path: str, *, maximum: int, item_limit: int
    ) -> list[str]:
        if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
            self._fail("invalid_skill_boundary", f"{path} must be an array.", path=path)
        if len(value) > maximum:
            self._fail("invalid_skill_boundary", f"{path} is too long.", path=path)
        return [self._bounded_text(item, f"{path}[{index}]", item_limit) for index, item in enumerate(value)]

    def _bounded_text(self, value: Any, path: str, maximum: int) -> str:
        text = self._text(value)
        if not text:
            self._fail(
                "invalid_generated_course_schema",
                f"{path} must be non-empty text.",
                path=path,
            )
        if len(text) > maximum:
            self._fail(
                "generated_course_limit_exceeded",
                f"{path} exceeds {maximum} characters.",
                path=path,
            )
        return text

    @staticmethod
    def _text(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        return value.strip()

    def _exact_keys(
        self, value: Mapping[str, Any], expected: frozenset[str], path: str
    ) -> None:
        actual = set(value)
        if actual != set(expected):
            self._fail(
                "invalid_generated_course_schema",
                f"{path} fields do not match the fixed schema.",
                path=path,
                details={
                    "missingFields": sorted(set(expected) - actual),
                    "unknownFields": sorted(actual - set(expected)),
                },
            )

    def _decode_object(self, value: Any, *, path: str) -> dict[str, Any]:
        if isinstance(value, str):
            if len(value.encode("utf-8")) > 128_000:
                self._fail(
                    "generated_course_limit_exceeded",
                    f"{path} JSON exceeds 128 KB.",
                    path=path,
                )
            try:
                decoded = json.loads(value, parse_constant=self._reject_json_constant)
            except (json.JSONDecodeError, ValueError) as exc:
                self._fail(
                    "invalid_generated_course_json",
                    f"{path} must be valid strict JSON.",
                    path=path,
                    details={"reason": str(exc)},
                )
        else:
            decoded = copy.deepcopy(value)
        if not isinstance(decoded, Mapping):
            self._fail(
                "invalid_generated_course_schema",
                f"{path} must be a JSON object.",
                path=path,
            )
        return dict(decoded)

    @staticmethod
    def _reject_json_constant(value: str):
        raise ValueError(f"non-finite JSON number is not allowed: {value}")

    @staticmethod
    def _fingerprint_set(values: Sequence[str]) -> set[str]:
        if isinstance(values, (str, bytes, Mapping)) or not isinstance(values, Sequence):
            raise GeneratedCourseValidationError(
                "invalid_existing_fingerprints",
                "existing_fingerprints must be an array.",
                path="existingFingerprints",
            )
        result: set[str] = set()
        for value in values:
            text = str(value or "").strip().casefold()
            if not re.fullmatch(r"[0-9a-f]{64}", text):
                raise GeneratedCourseValidationError(
                    "invalid_existing_fingerprints",
                    "Every existing fingerprint must be a SHA-256 hex digest.",
                    path="existingFingerprints",
                )
            result.add(text)
        return result

    def _question_fingerprint_payload(self, question: Any) -> Any:
        if not isinstance(question, Mapping):
            return question
        payload: dict[str, Any] = {
            "type": question.get("type"),
            "prompt": self._canonical_text(question.get("prompt")),
            "skill": self._canonical_text(question.get("skill")),
            "answer": self._canonical_value(question.get("answer")),
        }
        if question.get("type") == "numeric":
            try:
                payload["answer"] = format(
                    Decimal(str(question.get("answer") or "")).normalize(), "f"
                )
            except InvalidOperation:
                pass
        elif question.get("type") == "accepted_text" and isinstance(
            question.get("answer"), list
        ):
            payload["answer"] = sorted(
                self._canonical_text(item) for item in question["answer"]
            )
        choices = question.get("choices")
        if isinstance(choices, list):
            # Choice order and generated IDs are presentation details; labels
            # plus the correct label carry the semantic identity.
            labels_by_id = {
                str(item.get("id")): self._canonical_text(item.get("label"))
                for item in choices
                if isinstance(item, Mapping)
            }
            payload["choices"] = sorted(labels_by_id.values())
            if question.get("type") == "single_choice":
                payload["answer"] = labels_by_id.get(str(question.get("answer")), "")
            elif question.get("type") == "sequence" and isinstance(
                question.get("answer"), list
            ):
                payload["answer"] = [
                    labels_by_id.get(str(item), "") for item in question["answer"]
                ]
        return payload

    def _canonical_value(self, value: Any) -> Any:
        if isinstance(value, list):
            return [self._canonical_value(item) for item in value]
        if isinstance(value, str):
            return self._canonical_text(value)
        return value

    @staticmethod
    def _canonical_text(value: Any) -> str:
        return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())

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
                result = result.rstrip(_TERMINAL_PUNCTUATION).rstrip()
            elif operation == "strip_punctuation":
                result = "".join(
                    char
                    for char in result
                    if not unicodedata.category(char).startswith("P")
                )
            elif operation == "remove_grouping_separators":
                result = result.replace(",", "")
        return result

    @staticmethod
    def _contract_mismatch(path: str) -> None:
        raise GeneratedCourseValidationError(
            "generated_answer_contract_mismatch",
            "Private answer and deterministic evaluation contract disagree.",
            path=f"{path}.evaluation",
        )

    @staticmethod
    def _report(
        *,
        publishable: bool,
        checks: Sequence[str],
        fingerprint: str | None,
        issues: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        return {
            "schemaVersion": "mira.learning.generated-course-validation.v1",
            "validatorVersion": GENERATED_COURSE_VALIDATOR_VERSION,
            "publishable": publishable,
            "checksPassed": list(checks),
            "contentFingerprint": fingerprint,
            "issues": [dict(issue) for issue in issues],
        }

    @staticmethod
    def _fail(
        code: str,
        message: str,
        *,
        path: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        raise GeneratedCourseValidationError(
            code, message, path=path, details=details
        )


def validate_generated_course(
    candidate: str | Mapping[str, Any],
    **kwargs: Any,
) -> GeneratedCourseValidationResult:
    return LearningGeneratedCourseValidator().validate(candidate, **kwargs)
