from __future__ import annotations

import copy
import ast
from dataclasses import dataclass
import hashlib
import ipaddress
import json
import math
import re
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import MappingProxyType
from typing import Any, Literal, Mapping, Sequence
import unicodedata
from urllib.parse import urlsplit

from repositories.dynamic_learning_course_repository import (
    DynamicLearningCourseRepository,
)


QUESTION_GENERATION_INPUT_SCHEMA = "mira.openmaic.question_generation.v1"
QUESTION_CANDIDATES_OUTPUT_SCHEMA = "mira.openmaic.question_candidates.v1"
QUESTION_VERIFICATION_INPUT_SCHEMA = "mira.openmaic.question_verification.v1"
QUESTION_VERIFICATION_OUTPUT_SCHEMA = (
    "mira.openmaic.question_verification_result.v1"
)
QUESTION_CONSISTENCY_REPAIR_INPUT_SCHEMA = (
    "mira.openmaic.question_consistency_repair.v1"
)
QUESTION_CONSISTENCY_REPAIR_OUTPUT_SCHEMA = (
    "mira.openmaic.question_consistency_repair_result.v1"
)
TEACHING_FLOW_SCHEMA_VERSION = "mira.learning.teaching-flow.v1"
QUESTION_CONTRACT_VERSION = "mira.learning.question-contract.v2"
QUESTION_PHASE_INPUT_SCHEMA = "mira.openmaic.question_phase.v2"
QUESTION_PHASE_RESULT_SCHEMA = "mira.openmaic.question_phase_result.v2"
NUMBER_SENSE_CANONICAL_BUILDER_VERSION = (
    "mira.learning.number-sense-canonical-builder.v2"
)
LETTERS_SOUNDS_CANONICAL_BUILDER_VERSION = (
    "mira.learning.letters-sounds-canonical-builder.v2"
)
PRIMARY_ONE_ADD_SUB_HOST_SOLVER = (
    "host:primary-one-add-sub-v1:deterministic_public_question_solver"
)
PRIMARY_ONE_NUMBER_SENSE_HOST_SOLVER = (
    "host:primary-one-number-sense-v1:deterministic_public_question_solver"
)
PRIMARY_ONE_SIMPLE_SENTENCE_HOST_SOLVER = (
    "host:primary-one-simple-sentence-v1:deterministic_public_question_solver"
)
PRIMARY_ONE_CHARACTER_WORD_HOST_SOLVER = (
    "host:primary-one-character-word-v1:deterministic_public_question_solver"
)


def _is_exact_letters_sounds_phase(
    command: "QuestionPhaseCommand",
    phase: str,
    phase_ordinal: int,
) -> bool:
    return (
        command.phase == phase
        and command.phase_ordinal == phase_ordinal
        and command.grade_code == "primary_1"
        and command.subject == "english"
        and command.target_language_code == "en-US"
        and command.boundary.get("skillId") == "letters_sounds"
    )


def _is_exact_letters_sounds_phase3(command: "QuestionPhaseCommand") -> bool:
    return _is_exact_letters_sounds_phase(command, "candidate_repair", 3)


def _is_exact_letters_sounds_host_phase(command: "QuestionPhaseCommand") -> bool:
    return any(
        _is_exact_letters_sounds_phase(command, phase, phase_ordinal)
        for phase, phase_ordinal in (
            ("outline", 1),
            ("raw_candidate", 2),
            ("candidate_repair", 3),
        )
    )


def _is_exact_number_sense_phase(
    command: "QuestionPhaseCommand",
    phase: str,
    phase_ordinal: int,
) -> bool:
    return (
        command.phase == phase
        and command.phase_ordinal == phase_ordinal
        and command.grade_code == "primary_1"
        and command.subject == "math"
        and command.target_language_code == "zh-CN"
        and command.boundary.get("skillId") == "number_sense_20"
    )


def _is_exact_number_sense_phase3(command: "QuestionPhaseCommand") -> bool:
    return _is_exact_number_sense_phase(command, "candidate_repair", 3)


def _is_exact_number_sense_host_phase(command: "QuestionPhaseCommand") -> bool:
    return any(
        _is_exact_number_sense_phase(command, phase, phase_ordinal)
        for phase, phase_ordinal in (
            ("raw_candidate", 2),
            ("candidate_repair", 3),
        )
    )


def _is_exact_simple_sentence_host_phase(
    command: "QuestionPhaseCommand",
) -> bool:
    return (
        command.phase == "independent_verification"
        and command.phase_ordinal == 11
        and command.grade_code == "primary_1"
        and command.subject == "chinese"
        and command.target_language_code == "zh-CN"
        and command.boundary.get("skillId") == "simple_sentences"
    )


def _canonical_number_sense_raw_candidate_seed() -> dict[str, object]:
    return {
        "title": "20以内数感",
        "intro": "按固定技能边界准备数的顺序、大小和组成。",
        "estimatedMinutes": 10,
        "teachingFlow": {},
        "questions": [],
    }


def _canonical_letters_sounds_outline_plan() -> dict[str, object]:
    return {
        "courseTitle": "字母与发音基础",
        "languageDirective": "使用简体中文讲解。英文字母和目标单词使用英语。",
        "outlines": [
            {
                "order": 1,
                "title": "大小写字母与单词首音",
                "description": "按照大小写配对、首音辨认、示范、引导练习和独立练习组织课程。",
                "keyPoints": [
                    "配对大写与小写字母",
                    "辨认字母对应的单词首音",
                    "先观察字形,再听单词开头的声音",
                ],
            }
        ],
    }


def _canonical_letters_sounds_raw_candidate_seed() -> dict[str, object]:
    return {
        "title": "字母与发音基础",
        "intro": "按固定技能边界准备字母大小写配对和单词首音练习。",
        "estimatedMinutes": 10,
        "teachingFlow": {},
        "questions": [],
    }


def _phase_io(
    phase: str,
    phase_ordinal: int,
    input_keys: Sequence[str],
    accepted_keys: Sequence[str],
    rejected_keys: Sequence[str] | None,
) -> dict[str, object]:
    return {
        "phase": phase,
        "phaseOrdinal": phase_ordinal,
        "inputCheckpointKeys": list(input_keys),
        "acceptedCheckpointKeys": list(accepted_keys),
        "rejectedCheckpointKeys": list(rejected_keys) if rejected_keys else None,
    }


QUESTION_PHASE_IO = (
    _phase_io("outline", 1, ("questionCount", "existingFingerprints", "generationFeedback"), ("phaseStatus", "outlinePlan"), None),
    _phase_io("raw_candidate", 2, ("questionCount", "existingFingerprints", "generationFeedback", "outlinePlan"), ("phaseStatus", "rawCandidate"), None),
    _phase_io("candidate_repair", 3, ("questionCount", "existingFingerprints", "generationFeedback", "rawCandidate"), ("phaseStatus", "candidate", "hostCompilation"), ("phaseStatus", "rejectionCode")),
    _phase_io("candidate_repair_retry", 4, ("questionCount", "existingFingerprints", "generationFeedback", "rawCandidate", "priorRejectionCode"), ("phaseStatus", "candidate"), None),
    _phase_io("lesson_text", 5, ("candidate",), ("phaseStatus", "lessonText"), None),
    _phase_io("reconciliation", 6, ("questionCount", "existingFingerprints", "candidate", "lessonText"), ("phaseStatus", "reconciliation", "hostReconciliation"), ("phaseStatus", "rejectionCode")),
    _phase_io("reconciliation_retry", 7, ("questionCount", "existingFingerprints", "candidate", "lessonText", "priorRejectionCode"), ("phaseStatus", "reconciliation"), None),
    _phase_io("practice_leak_repair_1", 8, ("existingFingerprints", "candidate", "lessonText", "reconciliation", "leakingQuestionIndexes"), ("phaseStatus", "reconciliation"), None),
    _phase_io("practice_leak_repair_2", 9, ("existingFingerprints", "candidate", "lessonText", "reconciliation", "leakingQuestionIndexes"), ("phaseStatus", "reconciliation"), None),
    _phase_io("choice_prompt_repair", 10, ("existingFingerprints", "reconciliation", "violatingQuestionIndexes"), ("phaseStatus", "reconciliation"), None),
    _phase_io("independent_verification", 11, ("existingFingerprints", "outlinePlan", "candidate", "lessonText", "reconciliation"), ("phaseStatus", "candidateCourse", "questionFingerprints", "validation", "independentSolution"), None),
    _phase_io("consistency_repair", 12, ("candidateCourse", "independentSolution", "reviewIssues"), ("phaseStatus", "repair"), ("phaseStatus", "rejectionCode")),
    _phase_io("consistency_repair_retry", 13, ("candidateCourse", "independentSolution", "reviewIssues", "priorRejectionCode"), ("phaseStatus", "repair"), None),
    _phase_io("verification_after_repair", 14, ("existingFingerprints", "candidateCourse", "independentSolution", "questionFingerprints", "validation", "repair"), ("phaseStatus", "repairedCandidateCourse", "questionFingerprints", "validation", "independentSolution"), None),
)


def _transition_source(
    phase: str, phase_ordinal: int, phase_status: str, output_key: str
) -> dict[str, object]:
    return {
        "phase": phase,
        "phaseOrdinal": phase_ordinal,
        "phaseStatus": phase_status,
        "outputKey": output_key,
    }


def _transition_artifact(
    current_input_key: str, *sources: Mapping[str, object]
) -> dict[str, object]:
    return {"currentInputKey": current_input_key, "sources": [dict(item) for item in sources]}


def _transition(
    phase: str,
    phase_ordinal: int,
    artifacts: Sequence[Mapping[str, object]],
    branch_predicate: str,
) -> dict[str, object]:
    return {
        "phase": phase,
        "phaseOrdinal": phase_ordinal,
        "requiredSucceededArtifacts": [dict(item) for item in artifacts],
        "branchPredicate": branch_predicate,
    }


_CANDIDATE_SOURCES = (
    _transition_source("candidate_repair", 3, "accepted", "candidate"),
    _transition_source("candidate_repair_retry", 4, "accepted", "candidate"),
)
_BASE_RECONCILIATION_SOURCES = (
    _transition_source("reconciliation", 6, "accepted", "reconciliation"),
    _transition_source("reconciliation_retry", 7, "accepted", "reconciliation"),
)
_ALL_RECONCILIATION_SOURCES = (
    *_BASE_RECONCILIATION_SOURCES,
    _transition_source("practice_leak_repair_1", 8, "accepted", "reconciliation"),
    _transition_source("practice_leak_repair_2", 9, "accepted", "reconciliation"),
    _transition_source("choice_prompt_repair", 10, "accepted", "reconciliation"),
)
QUESTION_PHASE_TRANSITIONS = (
    _transition("outline", 1, (), "initial"),
    _transition("raw_candidate", 2, (_transition_artifact("outlinePlan", _transition_source("outline", 1, "accepted", "outlinePlan")),), "always"),
    _transition("candidate_repair", 3, (_transition_artifact("rawCandidate", _transition_source("raw_candidate", 2, "accepted", "rawCandidate")),), "always"),
    _transition("candidate_repair_retry", 4, (
        _transition_artifact("priorRejectionCode", _transition_source("candidate_repair", 3, "rejected", "rejectionCode")),
        _transition_artifact("rawCandidate", _transition_source("raw_candidate", 2, "accepted", "rawCandidate")),
    ), "candidate_repair_rejected"),
    _transition("lesson_text", 5, (_transition_artifact("candidate", *_CANDIDATE_SOURCES),), "always"),
    _transition("reconciliation", 6, (
        _transition_artifact("candidate", *_CANDIDATE_SOURCES),
        _transition_artifact("lessonText", _transition_source("lesson_text", 5, "accepted", "lessonText")),
    ), "always"),
    _transition("reconciliation_retry", 7, (
        _transition_artifact("priorRejectionCode", _transition_source("reconciliation", 6, "rejected", "rejectionCode")),
        _transition_artifact("candidate", *_CANDIDATE_SOURCES),
        _transition_artifact("lessonText", _transition_source("lesson_text", 5, "accepted", "lessonText")),
    ), "reconciliation_rejected"),
    _transition("practice_leak_repair_1", 8, (
        _transition_artifact("candidate", *_CANDIDATE_SOURCES),
        _transition_artifact("lessonText", _transition_source("lesson_text", 5, "accepted", "lessonText")),
        _transition_artifact("reconciliation", *_BASE_RECONCILIATION_SOURCES),
    ), "latest_reconciliation_has_practice_leaks"),
    _transition("practice_leak_repair_2", 9, (
        _transition_artifact("candidate", *_CANDIDATE_SOURCES),
        _transition_artifact("lessonText", _transition_source("lesson_text", 5, "accepted", "lessonText")),
        _transition_artifact("reconciliation", _transition_source("practice_leak_repair_1", 8, "accepted", "reconciliation")),
    ), "phase_8_reconciliation_still_has_practice_leaks"),
    _transition("choice_prompt_repair", 10, (_transition_artifact("reconciliation", *_ALL_RECONCILIATION_SOURCES[:-1]),), "latest_reconciliation_has_choice_prompt_violations"),
    _transition("independent_verification", 11, (
        _transition_artifact("outlinePlan", _transition_source("outline", 1, "accepted", "outlinePlan")),
        _transition_artifact("candidate", *_CANDIDATE_SOURCES),
        _transition_artifact("lessonText", _transition_source("lesson_text", 5, "accepted", "lessonText")),
        _transition_artifact("reconciliation", *_ALL_RECONCILIATION_SOURCES),
    ), "latest_reconciliation_is_clean"),
    _transition("consistency_repair", 12, (
        _transition_artifact("candidateCourse", _transition_source("independent_verification", 11, "accepted", "candidateCourse")),
        _transition_artifact("independentSolution", _transition_source("independent_verification", 11, "accepted", "independentSolution")),
    ), "phase_11_teaching_review_failed"),
    _transition("consistency_repair_retry", 13, (
        _transition_artifact("candidateCourse", _transition_source("independent_verification", 11, "accepted", "candidateCourse")),
        _transition_artifact("independentSolution", _transition_source("independent_verification", 11, "accepted", "independentSolution")),
        _transition_artifact("priorRejectionCode", _transition_source("consistency_repair", 12, "rejected", "rejectionCode")),
    ), "consistency_repair_rejected"),
    _transition("verification_after_repair", 14, (
        _transition_artifact("candidateCourse", _transition_source("independent_verification", 11, "accepted", "candidateCourse")),
        _transition_artifact("independentSolution", _transition_source("independent_verification", 11, "accepted", "independentSolution")),
        _transition_artifact("questionFingerprints", _transition_source("independent_verification", 11, "accepted", "questionFingerprints")),
        _transition_artifact("validation", _transition_source("independent_verification", 11, "accepted", "validation")),
        _transition_artifact("repair",
            _transition_source("consistency_repair", 12, "accepted", "repair"),
            _transition_source("consistency_repair_retry", 13, "accepted", "repair"),
        ),
    ), "phase_11_teaching_review_failed_and_consistency_repair_accepted"),
)

QUESTION_PHASE_EXECUTION_AUTHORITY = tuple(
    {
        "phase": row["phase"],
        "phaseOrdinal": row["phaseOrdinal"],
        "providerRole": (
            "verifier"
            if row["phaseOrdinal"] in (11, 14)
            else "generator"
        ),
        "finalCandidateKey": (
            "candidateCourse"
            if row["phaseOrdinal"] == 11
            else (
                "repairedCandidateCourse"
                if row["phaseOrdinal"] == 14
                else None
            )
        ),
    }
    for row in QUESTION_PHASE_IO
)


def _freeze_phase_authority(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze_phase_authority(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_phase_authority(item) for item in value)
    return value


QUESTION_PHASE_IO = _freeze_phase_authority(QUESTION_PHASE_IO)
QUESTION_PHASE_TRANSITIONS = _freeze_phase_authority(QUESTION_PHASE_TRANSITIONS)
QUESTION_PHASE_EXECUTION_AUTHORITY = _freeze_phase_authority(
    QUESTION_PHASE_EXECUTION_AUTHORITY
)


def question_phase_execution_authority(
    phase: object,
    phase_ordinal: object,
) -> Mapping[str, object]:
    for row in QUESTION_PHASE_EXECUTION_AUTHORITY:
        if row["phase"] == phase and row["phaseOrdinal"] == phase_ordinal:
            return row
    raise ValueError("question phase execution authority is invalid")

_QUESTION_PHASE_REQUEST_KEYS = {
    "schemaVersion", "questionContractVersion", "requestId", "phase",
    "phaseOrdinal", "gradeCode", "subject", "instructionLanguageCode",
    "targetLanguageCode", "skillBoundary", "checkpoint", "provider", "mode",
    "fakeResponses",
}
_QUESTION_PHASE_RESULT_KEYS = {
    "schemaVersion", "questionContractVersion", "requestId", "phase",
    "phaseOrdinal", "outcome", "checkpoint", "providerRequestIdHash",
    "inputTokens", "outputTokens", "billingEvidence", "safeErrorCode",
    "elapsedMs",
}
_QUESTION_PHASE_SKILL_KEYS = (
    "skillId", "skillTitle", "learningObjectives", "allowedContent",
    "excludedContent", "prerequisiteSkills", "estimatedMinutes",
)
_QUESTION_PHASE_PROVIDER_KEYS = (
    "name", "model", "baseUrl", "apiKeyEnv", "timeoutMs", "maxTokens",
    "temperature",
)
_AMBIGUOUS_SAFE_CODES = frozenset({
    "provider_timeout", "provider_connection_interrupted",
    "provider_response_lost", "provider_outcome_unknown",
})
_FAILED_SAFE_CODES = frozenset({
    "question_phase_invalid_input", "question_phase_contract_drift",
    "question_phase_unsupported", "question_phase_preflight_rejected",
    "question_phase_output_rejected", "question_phase_json_rejected",
    "provider_unavailable",
    "provider_request_rejected", "provider_no_candidate",
    "provider_invalid_response",
    "question_phase_verification_json_rejected",
    "question_phase_verification_answers_rejected",
    "question_phase_verification_numeric_rejected",
    "question_phase_verification_review_rejected",
    "question_phase_verification_semantic_rejected",
    "question_phase_verification_checkpoint_rejected",
})
_STORED_FAILED_SAFE_CODES = _FAILED_SAFE_CODES | frozenset(
    {"phase_deadline_insufficient", "phase_lease_lost"}
)


@dataclass(frozen=True)
class QuestionPhaseCommand:
    build_item_id: str
    logical_attempt: int
    phase: str
    phase_ordinal: int
    generation_request_id: str
    grade_code: str
    subject: str
    instruction_language_code: str
    target_language_code: str
    boundary: Mapping[str, object]
    checkpoint: Mapping[str, object]
    difficulty_code: str | None = None


@dataclass(frozen=True)
class QuestionPhaseResult:
    request_id: str
    phase: str
    phase_ordinal: int
    outcome: Literal["succeeded", "failed_safe", "ambiguous"]
    checkpoint: Mapping[str, object] | None
    provider_request_id_hash: str | None
    input_tokens: int | None
    output_tokens: int | None
    billing_evidence: Literal["reported", "unknown"]
    safe_error_code: str | None
    elapsed_ms: float


@dataclass(frozen=True)
class PreparedQuestionPhase:
    command: QuestionPhaseCommand
    request: Mapping[str, object]
    canonical_input_json: str
    input_sha256: str
    provider: Mapping[str, object]
    canonical_profile_json: str
    profile_sha256: str


class OpenMaicQuestionPhaseAdapter:
    """Strict V2 one-process/one-Provider phase boundary."""

    PROCESS_SHUTDOWN_ALLOWANCE_MS = 5_000
    PERSISTENCE_MARGIN_MS = 10_000

    def __init__(
        self,
        *,
        sidecar_root: str | Path | None = None,
        node_binary: str = "node",
        provider_name: str | None = None,
        model_name: str | None = None,
        base_url: str | None = None,
        api_key_env: str = "APP_AI_API_KEY",
        provider_timeout_ms: int = 300_000,
        max_tokens: int = 8_000,
        temperature: float = 0.2,
        process_timeout_seconds: float = 305.0,
        process_runner=subprocess.run,
        paid_budget_environment=None,
    ):
        backend_root = Path(__file__).resolve().parents[1]
        self.sidecar_root = Path(
            sidecar_root or backend_root / "openmaic-sidecar"
        ).resolve()
        self.node_binary = str(node_binary)
        if type(provider_timeout_ms) is not int or not 1_000 <= provider_timeout_ms <= 300_000:
            raise ValueError("V2 provider timeout must be between 1000 and 300000ms")
        if (
            isinstance(process_timeout_seconds, bool)
            or not isinstance(process_timeout_seconds, (int, float))
            or not math.isfinite(float(process_timeout_seconds))
            or not 1 <= float(process_timeout_seconds) <= 305
        ):
            raise ValueError("V2 process timeout must be between 1 and 305 seconds")
        if type(max_tokens) is not int or not 512 <= max_tokens <= 32_000:
            raise ValueError("V2 max tokens is invalid")
        if (
            isinstance(temperature, bool)
            or not isinstance(temperature, (int, float))
            or not math.isfinite(float(temperature))
            or not 0 <= float(temperature) <= 1
        ):
            raise ValueError("V2 temperature is invalid")
        self.paid_budget_environment = paid_budget_environment
        self.provider_name = str(provider_name or os.getenv("APP_AI_PROVIDER") or "kimi").strip()
        self.model_name = str(model_name or os.getenv("APP_AI_MODEL") or "").strip()
        self.base_url = str(base_url or os.getenv("APP_AI_BASE_URL") or "")
        self.api_key_env = str(api_key_env).strip()
        self.provider_timeout_ms = provider_timeout_ms
        self.max_tokens = max_tokens
        self.temperature = float(temperature)
        self.process_timeout_seconds = float(process_timeout_seconds)
        self._run = process_runner

    @property
    def cli_path(self) -> Path:
        return self.sidecar_root / "src" / "cli.mjs"

    @property
    def required_phase_budget_ms(self) -> int:
        provider_budget = self.provider_timeout_ms + self.PROCESS_SHUTDOWN_ALLOWANCE_MS
        process_budget = math.ceil(self.process_timeout_seconds * 1000)
        return max(provider_budget, process_budget) + self.PERSISTENCE_MARGIN_MS

    def preflight_phase(self, command: QuestionPhaseCommand) -> PreparedQuestionPhase:
        if not isinstance(command, QuestionPhaseCommand):
            raise ValueError("question phase command is invalid")
        if not self.cli_path.is_file() or shutil.which(self.node_binary) is None:
            raise ValueError("OpenMAIC question phase sidecar is unavailable")
        prepared = self.canonicalize_phase(command)
        if (
            _is_exact_letters_sounds_host_phase(command)
            or _is_exact_number_sense_host_phase(command)
            or _is_exact_simple_sentence_host_phase(command)
        ):
            return prepared
        if not self.model_name or not self.base_url or not os.getenv(self.api_key_env, "").strip():
            raise ValueError("OpenMAIC question phase provider is unavailable")
        return prepared

    def canonicalize_phase(
        self, command: QuestionPhaseCommand
    ) -> PreparedQuestionPhase:
        """Build canonical Task-5 request/hash authority without availability I/O."""
        if not isinstance(command, QuestionPhaseCommand):
            raise ValueError("question phase command is invalid")
        _require_identifier(command.build_item_id, "build item")
        _require_request_id(command.generation_request_id)
        if type(command.logical_attempt) is not int or command.logical_attempt not in (1, 2):
            raise ValueError("logical attempt must be one or two")
        io = _phase_io_for(command.phase, command.phase_ordinal)
        from content.formal_curriculum_registry import formal_registered_boundary
        from content.formal_objective_rules import objective_question_policy
        registered_boundary = formal_registered_boundary(
            command.grade_code, command.subject, command.boundary.get("skillId")
        ) if command.grade_code != "primary_1" else None
        if command.subject not in {"chinese", "math", "english"}:
            raise ValueError("subject is invalid")
        expected_target = "en-US" if command.subject == "english" else "zh-CN"
        if command.instruction_language_code != "zh-CN" or command.target_language_code != expected_target:
            raise ValueError("language codes are not canonical for subject")
        provider = normalize_question_phase_provider_profile({
            "name": self.provider_name,
            "model": self.model_name,
            "baseUrl": self.base_url,
            "apiKeyEnv": self.api_key_env,
            "timeoutMs": self.provider_timeout_ms,
            "maxTokens": self.max_tokens,
            "temperature": self.temperature,
        })
        boundary = _normalize_phase_boundary(command.boundary)
        if command.grade_code != "primary_1":
            expected_boundary = registered_boundary.to_catalog_payload()
            if any(boundary[key] != expected_boundary[key] for key in boundary):
                raise ValueError("formal grade skill boundary drift")
        checkpoint = _normalize_phase_checkpoint(
            command,
            io,
            command.checkpoint,
            provider=provider,
        )
        request = {
            "schemaVersion": QUESTION_PHASE_INPUT_SCHEMA,
            "questionContractVersion": QUESTION_CONTRACT_VERSION,
            "requestId": command.generation_request_id,
            "phase": command.phase,
            "phaseOrdinal": command.phase_ordinal,
            "gradeCode": command.grade_code,
            "subject": command.subject,
            "instructionLanguageCode": command.instruction_language_code,
            "targetLanguageCode": command.target_language_code,
            "skillBoundary": boundary,
            "checkpoint": checkpoint,
            "provider": provider,
            "mode": "live",
            "fakeResponses": [],
        }
        if command.grade_code != "primary_1":
            request["objectivePolicy"] = json.loads(json.dumps(objective_question_policy(command.grade_code, command.subject, boundary["skillId"], command.difficulty_code), ensure_ascii=False))
        expected_keys = _QUESTION_PHASE_REQUEST_KEYS | ({"objectivePolicy"} if command.grade_code != "primary_1" else set())
        if set(request) != expected_keys:
            raise ValueError("question phase request fields mismatch")
        canonical_input = _canonical_json(request)
        canonical_profile = _canonical_json(provider)
        return PreparedQuestionPhase(
            command=command,
            request=request,
            canonical_input_json=canonical_input,
            input_sha256=hashlib.sha256(canonical_input.encode("utf-8")).hexdigest(),
            provider=provider,
            canonical_profile_json=canonical_profile,
            profile_sha256=hashlib.sha256(canonical_profile.encode("utf-8")).hexdigest(),
        )

    def execute_phase(self, prepared: PreparedQuestionPhase) -> QuestionPhaseResult:
        if not isinstance(prepared, PreparedQuestionPhase):
            raise ValueError("prepared question phase is invalid")
        environment = os.environ.copy()
        environment['OPENMAIC_HOST_VALIDATOR_PYTHON'] = sys.executable
        for key in ("MIRA_PAID_BUDGET_BINDING", "MIRA_PAID_BUDGET_BACKEND_URL", "MIRA_PAID_BUDGET_INTERNAL_TOKEN"):
            environment.pop(key, None)
        if self.paid_budget_environment is not None:
            try:
                environment.update(self.paid_budget_environment(prepared.command))
            except Exception:
                return self._failed_safe_result(prepared, "provider_unavailable")
        elif prepared.command.grade_code != "primary_1":
            return self._failed_safe_result(prepared, "provider_unavailable")
        try:
            completed = self._run(
                [self.node_binary, str(self.cli_path), "--question-phase-v2"],
                cwd=str(self.sidecar_root),
                input=prepared.canonical_input_json,
                text=True,
                capture_output=True,
                timeout=self.process_timeout_seconds,
                env=environment,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return self._control_result(prepared, "provider_timeout")
        except (FileNotFoundError, PermissionError) as exc:
            if getattr(exc, "child_started", False) is True:
                return self._control_result(prepared, "provider_outcome_unknown")
            return self._failed_safe_result(prepared, "provider_unavailable")
        except OSError:
            return self._control_result(prepared, "provider_outcome_unknown")
        if type(completed.returncode) is not int or completed.returncode < 0:
            return self._control_result(prepared, "provider_outcome_unknown")
        try:
            payload = json.loads(str(completed.stdout or ""))
            return self._normalize_result(
                prepared, payload, returncode=completed.returncode
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            return self._control_result(prepared, "provider_outcome_unknown")

    def _normalize_stored_dispatch_result(
        self, prepared: PreparedQuestionPhase, dispatch: Mapping[str, object]
    ) -> QuestionPhaseResult:
        status = str(dispatch.get("status") or "")
        if status == "succeeded":
            raw_checkpoint = dispatch.get("checkpoint_json")
            if not isinstance(raw_checkpoint, str):
                raise ValueError("stored dispatch checkpoint is absent")
            checkpoint = json.loads(raw_checkpoint)
            normalized = _normalize_phase_output_checkpoint(prepared, checkpoint)
            canonical = _canonical_json(normalized)
            if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != dispatch.get("output_sha256"):
                raise ValueError("stored dispatch checkpoint hash mismatch")
            return QuestionPhaseResult(
                request_id=prepared.command.generation_request_id,
                phase=prepared.command.phase,
                phase_ordinal=prepared.command.phase_ordinal,
                outcome="succeeded",
                checkpoint=normalized,
                provider_request_id_hash=_nullable_sha256(dispatch.get("provider_request_id_hash")),
                input_tokens=_nullable_safe_integer(dispatch.get("input_tokens")),
                output_tokens=_nullable_safe_integer(dispatch.get("output_tokens")),
                billing_evidence=_billing_evidence(
                    dispatch.get("billing_evidence"),
                    dispatch.get("input_tokens"),
                    dispatch.get("output_tokens"),
                ),
                safe_error_code=None,
                elapsed_ms=0.0,
            )
        if status not in {"failed_safe", "ambiguous"}:
            raise ValueError("stored dispatch is not terminal")
        code = str(dispatch.get("safe_error_code") or "")
        expected_codes = _STORED_FAILED_SAFE_CODES if status == "failed_safe" else _AMBIGUOUS_SAFE_CODES
        if code not in expected_codes:
            raise ValueError("stored dispatch safe error pairing is invalid")
        return QuestionPhaseResult(
            request_id=prepared.command.generation_request_id,
            phase=prepared.command.phase,
            phase_ordinal=prepared.command.phase_ordinal,
            outcome=status,
            checkpoint=None,
            provider_request_id_hash=_nullable_sha256(dispatch.get("provider_request_id_hash")),
            input_tokens=_nullable_safe_integer(dispatch.get("input_tokens")),
            output_tokens=_nullable_safe_integer(dispatch.get("output_tokens")),
            billing_evidence=_billing_evidence(
                dispatch.get("billing_evidence"),
                dispatch.get("input_tokens"),
                dispatch.get("output_tokens"),
            ),
            safe_error_code=code,
            elapsed_ms=0.0,
        )

    def _normalize_result(
        self,
        prepared: PreparedQuestionPhase,
        payload: object,
        *,
        returncode: int,
    ) -> QuestionPhaseResult:
        value = _plain_mapping(payload, "question phase result")
        _require_exact_keys(value, _QUESTION_PHASE_RESULT_KEYS, "question phase result")
        command = prepared.command
        if (
            value.get("schemaVersion") != QUESTION_PHASE_RESULT_SCHEMA
            or value.get("questionContractVersion") != QUESTION_CONTRACT_VERSION
            or value.get("requestId") != command.generation_request_id
            or value.get("phase") != command.phase
            or type(value.get("phaseOrdinal")) is not int
            or value.get("phaseOrdinal") != command.phase_ordinal
        ):
            raise ValueError("question phase result identity mismatch")
        outcome = value.get("outcome")
        if outcome not in {"succeeded", "failed_safe", "ambiguous"}:
            raise ValueError("question phase result outcome is invalid")
        if (outcome == "succeeded") != (returncode == 0):
            raise ValueError("question phase process outcome contradicts return code")
        safe_error = value.get("safeErrorCode")
        checkpoint = value.get("checkpoint")
        if outcome == "succeeded":
            if safe_error is not None:
                raise ValueError("successful phase contains a safe error")
            checkpoint = _normalize_phase_output_checkpoint(prepared, checkpoint)
        else:
            if checkpoint is not None or not isinstance(safe_error, str):
                raise ValueError("failed phase receipt pairing is invalid")
            allowed = _FAILED_SAFE_CODES if outcome == "failed_safe" else _AMBIGUOUS_SAFE_CODES
            if safe_error not in allowed:
                raise ValueError("failed phase safe code pairing is invalid")
        request_hash = _nullable_sha256(value.get("providerRequestIdHash"))
        input_tokens = _nullable_safe_integer(value.get("inputTokens"))
        output_tokens = _nullable_safe_integer(value.get("outputTokens"))
        billing = _billing_evidence(
            value.get("billingEvidence"), input_tokens, output_tokens
        )
        elapsed = value.get("elapsedMs")
        if (
            isinstance(elapsed, bool)
            or not isinstance(elapsed, (int, float))
            or not math.isfinite(float(elapsed))
            or elapsed < 0
        ):
            raise ValueError("question phase elapsed evidence is invalid")
        return QuestionPhaseResult(
            request_id=command.generation_request_id,
            phase=command.phase,
            phase_ordinal=command.phase_ordinal,
            outcome=outcome,
            checkpoint=checkpoint,
            provider_request_id_hash=request_hash,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            billing_evidence=billing,
            safe_error_code=safe_error,
            elapsed_ms=float(elapsed),
        )

    @staticmethod
    def _control_result(
        prepared: PreparedQuestionPhase, code: str
    ) -> QuestionPhaseResult:
        return QuestionPhaseResult(
            request_id=prepared.command.generation_request_id,
            phase=prepared.command.phase,
            phase_ordinal=prepared.command.phase_ordinal,
            outcome="ambiguous",
            checkpoint=None,
            provider_request_id_hash=None,
            input_tokens=None,
            output_tokens=None,
            billing_evidence="unknown",
            safe_error_code=code,
            elapsed_ms=0.0,
        )

    @staticmethod
    def _failed_safe_result(
        prepared: PreparedQuestionPhase, code: str
    ) -> QuestionPhaseResult:
        return QuestionPhaseResult(
            request_id=prepared.command.generation_request_id,
            phase=prepared.command.phase,
            phase_ordinal=prepared.command.phase_ordinal,
            outcome="failed_safe",
            checkpoint=None,
            provider_request_id_hash=None,
            input_tokens=None,
            output_tokens=None,
            billing_evidence="unknown",
            safe_error_code=code,
            elapsed_ms=0.0,
        )


def _canonical_json(value: object) -> str:
    _assert_bounded_json(value, "canonical value")
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _plain_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _require_exact_keys(value: Mapping[str, object], expected: Sequence[str] | set[str], field: str) -> None:
    if set(value) != set(expected) or len(value) != len(set(expected)):
        raise ValueError(f"{field} fields mismatch")


def _require_identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@/+-]{0,127}", value):
        raise ValueError(f"{field} identity is invalid")
    return value


def _require_request_id(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}", value
    ):
        raise ValueError("question phase requestId is invalid")
    return value


_V2_HTML_ENTITY = re.compile(
    r"&(#x[0-9a-f]+|#\d+|amp|apos|gt|lt|nbsp|quot);",
    flags=re.IGNORECASE,
)
_V2_NAMED_HTML_ENTITIES = {
    "amp": "&",
    "apos": "'",
    "gt": ">",
    "lt": "<",
    "nbsp": " ",
    "quot": '"',
}


def _decode_v2_html_entities(value: str) -> str:
    def replace_entity(match: re.Match[str]) -> str:
        entity = match.group(1).lower()
        if entity.startswith("#x"):
            code_point = int(entity[2:], 16)
        elif entity.startswith("#"):
            code_point = int(entity[1:], 10)
        else:
            return _V2_NAMED_HTML_ENTITIES.get(entity, match.group(0))
        if not 0 <= code_point <= 0x10FFFF or 0xD800 <= code_point <= 0xDFFF:
            return match.group(0)
        return chr(code_point)

    return _V2_HTML_ENTITY.sub(replace_entity, value)


def _utf16_length(value: str) -> int:
    return len(value.encode("utf-16-le", errors="surrogatepass")) // 2


def _normalized_string(value: object, field: str, *, maximum: int = 500) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    normalized = _decode_v2_html_entities(
        unicodedata.normalize("NFKC", value).strip()
    )
    normalized = re.sub(
        r"<\s*(script|style)\b[^>]*>[\s\S]*?<\s*/\s*\1\s*>",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"<\s*br\s*/?>", "\n", normalized, flags=re.IGNORECASE)
    normalized = re.sub(
        r"<\s*/\s*(p|div|li|h[1-6])\s*>",
        "\n",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"<[^>]*>", "", normalized)
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n[ \t]+", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if not normalized or _utf16_length(normalized) > maximum:
        raise ValueError(f"{field} is invalid")
    return normalized


def _normalized_string_array(
    value: object,
    field: str,
    *,
    minimum: int = 0,
    maximum: int = 30,
    string_maximum: int = 500,
) -> list[str]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{field} item count is invalid")
    result = [
        _normalized_string(item, f"{field}[{index}]", maximum=string_maximum)
        for index, item in enumerate(value)
    ]
    if len(set(result)) != len(result):
        raise ValueError(f"{field} contains duplicates")
    return result


def _normalize_phase_boundary(raw: Mapping[str, object]) -> dict[str, object]:
    value = _plain_mapping(raw, "skillBoundary")
    allowed_source_keys = set(_QUESTION_PHASE_SKILL_KEYS) | {"language"}
    if set(value) - allowed_source_keys or not set(_QUESTION_PHASE_SKILL_KEYS).issubset(value):
        raise ValueError("skillBoundary fields mismatch")
    estimated = value.get("estimatedMinutes")
    if type(estimated) is not int or not 5 <= estimated <= 30:
        raise ValueError("skillBoundary.estimatedMinutes is invalid")
    return {
        "skillId": _normalized_string(value.get("skillId"), "skillBoundary.skillId", maximum=120),
        "skillTitle": _normalized_string(value.get("skillTitle"), "skillBoundary.skillTitle", maximum=160),
        "learningObjectives": _normalized_string_array(value.get("learningObjectives"), "skillBoundary.learningObjectives", minimum=1, maximum=12),
        "allowedContent": _normalized_string_array(value.get("allowedContent"), "skillBoundary.allowedContent", minimum=1, maximum=30),
        "excludedContent": _normalized_string_array(value.get("excludedContent"), "skillBoundary.excludedContent", maximum=30),
        "prerequisiteSkills": _normalized_string_array(value.get("prerequisiteSkills"), "skillBoundary.prerequisiteSkills", maximum=12),
        "estimatedMinutes": estimated,
    }


def normalize_question_phase_provider_profile(
    raw: Mapping[str, object],
) -> dict[str, object]:
    value = _plain_mapping(raw, "provider")
    _require_exact_keys(value, _QUESTION_PHASE_PROVIDER_KEYS, "provider")
    timeout = value.get("timeoutMs")
    max_tokens = value.get("maxTokens")
    temperature = value.get("temperature")
    if type(timeout) is not int or not 1_000 <= timeout <= 300_000:
        raise ValueError("provider.timeoutMs is invalid")
    if type(max_tokens) is not int or not 512 <= max_tokens <= 32_000:
        raise ValueError("provider.maxTokens is invalid")
    if (
        isinstance(temperature, bool)
        or not isinstance(temperature, (int, float))
        or not math.isfinite(float(temperature))
        or not 0 <= float(temperature) <= 1
    ):
        raise ValueError("provider.temperature is invalid")
    api_key_env = _normalized_string(value.get("apiKeyEnv"), "provider.apiKeyEnv", maximum=80)
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", api_key_env):
        raise ValueError("provider.apiKeyEnv is invalid")
    name = _normalized_storage_text(
        _normalized_string(value.get("name"), "provider.name", maximum=80),
        "provider.name",
    )
    model = _normalized_storage_text(
        _normalized_string(value.get("model"), "provider.model", maximum=160),
        "provider.model",
    )
    base_url = _normalize_absolute_http_url(value.get("baseUrl"))
    return {
        "name": name,
        "model": model,
        "baseUrl": base_url,
        "apiKeyEnv": api_key_env,
        "timeoutMs": timeout,
        "maxTokens": max_tokens,
        "temperature": float(temperature),
    }


def _normalize_phase_provider(raw: Mapping[str, object]) -> dict[str, object]:
    return normalize_question_phase_provider_profile(raw)


def _normalize_absolute_http_url(value: object) -> str:
    error = "provider.baseUrl must be a strict absolute HTTP(S) URL"
    if (
        not isinstance(value, str)
        or not value
        or _utf16_length(value) > 500
        or any(
            character.isspace()
            or ord(character) < 0x20
            or ord(character) == 0x7F
            for character in value
        )
    ):
        raise ValueError(error)
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ValueError(error) from exc
    if unicodedata.normalize("NFKC", value) != value:
        raise ValueError(error)

    normalized = value
    if "<" in normalized or ">" in normalized:
        raise ValueError(error)

    try:
        parsed = urlsplit(normalized)
        port = parsed.port
        hostname = parsed.hostname
    except (TypeError, ValueError) as exc:
        raise ValueError(error) from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or "%" in hostname
    ):
        raise ValueError(error)
    if port is not None and not 0 <= port <= 65_535:
        raise ValueError(error)

    try:
        if ":" in hostname:
            bracketed = re.fullmatch(
                r"\[([^\]]+)\](?::([0-9]+))?", parsed.netloc
            )
            if bracketed is None or bracketed.group(1) != hostname:
                raise ValueError(error)
            ipaddress.IPv6Address(hostname)
        elif re.fullmatch(r"[0-9.]+", hostname):
            address = ipaddress.IPv4Address(hostname)
            if str(address) != hostname:
                raise ValueError(error)
        else:
            label_host = hostname[:-1] if hostname.endswith(".") else hostname
            ascii_host = label_host.encode("idna").decode("ascii")
            if not ascii_host or len(ascii_host) > 253:
                raise ValueError(error)
            labels = ascii_host.split(".")
            if labels[-1].isdigit() or any(
                not 1 <= len(label) <= 63
                or re.fullmatch(
                    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?",
                    label,
                )
                is None
                for label in labels
            ):
                raise ValueError(error)
    except (UnicodeError, ipaddress.AddressValueError) as exc:
        raise ValueError(error) from exc
    return normalized


def _normalized_storage_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError(f"{field} exceeds the formal persistence profile")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{field} is not valid UTF-8 text") from exc
    return value


def _phase_io_for(phase: object, phase_ordinal: object) -> Mapping[str, object]:
    if not isinstance(phase, str) or type(phase_ordinal) is not int:
        raise ValueError("phase identity is invalid")
    for item in QUESTION_PHASE_IO:
        if item["phase"] == phase:
            if item["phaseOrdinal"] != phase_ordinal:
                raise ValueError("phase ordinal mismatch")
            return item
    raise ValueError("unsupported question phase")


def _normalize_phase_checkpoint(
    command: QuestionPhaseCommand,
    io: Mapping[str, object],
    raw: Mapping[str, object],
    *,
    provider: Mapping[str, object],
) -> dict[str, object]:
    value = _plain_mapping(raw, "checkpoint")
    expected = io["inputCheckpointKeys"]
    assert isinstance(expected, tuple)
    _require_exact_keys(value, expected, "checkpoint")
    result: dict[str, object] = {}
    for key in expected:
        item = value[key]
        if key == "questionCount":
            if type(item) is not int or item != 5:
                raise ValueError("checkpoint.questionCount must be 5")
            result[key] = 5
        elif key == "existingFingerprints":
            fingerprints = _normalized_string_array(
                item, "checkpoint.existingFingerprints", maximum=500, string_maximum=64
            )
            if any(not re.fullmatch(r"[a-f0-9]{64}", fingerprint) for fingerprint in fingerprints):
                raise ValueError("checkpoint.existingFingerprints is invalid")
            result[key] = fingerprints
        elif key == "generationFeedback":
            if item is None:
                result[key] = None
            else:
                feedback = _plain_mapping(item, "checkpoint.generationFeedback")
                _require_exact_keys(feedback, {"code", "message"}, "checkpoint.generationFeedback")
                result[key] = {
                    "code": _normalized_string(feedback.get("code"), "checkpoint.generationFeedback.code", maximum=128),
                    "message": _normalized_string(feedback.get("message"), "checkpoint.generationFeedback.message", maximum=512),
                }
        elif key == "outlinePlan":
            result[key] = _normalize_outline_plan(item)
        elif key == "rawCandidate":
            if (
                _is_exact_letters_sounds_phase3(command)
                or _is_exact_number_sense_phase3(command)
            ):
                try:
                    result[key] = _normalize_candidate_projection(
                        item, command, compiled=False, require_canonical=True
                    )
                except ValueError:
                    # The exact Host builder owns every question and answer. Keep
                    # malformed Provider phase-2 data only as a null audit marker.
                    result[key] = None
            else:
                result[key] = _normalize_candidate_projection(
                    item, command, compiled=False, require_canonical=True
                )
        elif key == "candidate":
            inventory = result.get("existingFingerprints", [])
            assert isinstance(inventory, list)
            result[key] = _normalize_candidate_projection(
                item,
                command,
                compiled=True,
                require_canonical=True,
                existing_fingerprints=inventory,
            )
        elif key == "lessonText":
            result[key] = _normalize_lesson_text(item)
        elif key == "reconciliation":
            inventory = result.get("existingFingerprints", [])
            assert isinstance(inventory, list)
            result[key] = _normalize_reconciliation(
                item, command, existing_fingerprints=inventory
            )
        elif key in {"leakingQuestionIndexes", "violatingQuestionIndexes"}:
            result[key] = _normalize_question_indexes(item, f"checkpoint.{key}")
        elif key == "priorRejectionCode":
            result[key] = _normalize_prior_rejection(command.phase, item)
        elif key == "candidateCourse":
            inventory = result.get("existingFingerprints", [])
            assert isinstance(inventory, list)
            result[key] = _normalize_candidate_course(
                item, command, existing_fingerprints=inventory
            )
        elif key == "independentSolution":
            course = result.get("candidateCourse")
            if not isinstance(course, Mapping):
                raise ValueError("independentSolution requires candidateCourse")
            result[key] = _normalize_independent_solution(
                item, command, course, provider=provider
            )
        elif key == "questionFingerprints":
            result[key] = _normalize_question_fingerprints(item)
        elif key == "validation":
            result[key] = _normalize_validation(item)
        elif key == "reviewIssues":
            result[key] = _normalized_string_array(
                item,
                "checkpoint.reviewIssues",
                minimum=1,
                maximum=3,
                string_maximum=300,
            )
        elif key == "repair":
            course = result.get("candidateCourse")
            if not isinstance(course, Mapping):
                raise ValueError("repair requires candidateCourse")
            result[key] = _normalize_consistency_repair(item, course, command)
        else:
            result[key] = _assert_bounded_json(item, f"checkpoint.{key}")

    if command.phase in {"practice_leak_repair_1", "practice_leak_repair_2"}:
        expected_indexes = _practice_leak_indexes(
            result["lessonText"]["teachingFlow"],
            result["reconciliation"]["questions"],
        )
        if not expected_indexes or expected_indexes != result["leakingQuestionIndexes"]:
            raise ValueError("checkpoint.leakingQuestionIndexes is stale or forged")
    if command.phase == "choice_prompt_repair":
        expected_indexes = _choice_prompt_violation_indexes(
            result["reconciliation"]["questions"]
        )
        if not expected_indexes or expected_indexes != result["violatingQuestionIndexes"]:
            raise ValueError("checkpoint.violatingQuestionIndexes is stale or forged")
    if command.phase == "independent_verification":
        if _practice_leak_indexes(
            result["lessonText"]["teachingFlow"],
            result["reconciliation"]["questions"],
        ) or _choice_prompt_violation_indexes(result["reconciliation"]["questions"]):
            raise ValueError("phase 11 requires a clean latest reconciliation")
    if command.phase in {"consistency_repair", "consistency_repair_retry"}:
        review = result["independentSolution"]["teachingReview"]
        if review["passed"] is not False or review["issues"] != result["reviewIssues"]:
            raise ValueError("reviewIssues must equal the internal teaching review")
    if command.phase == "verification_after_repair":
        course = result["candidateCourse"]
        expected_fingerprints = _build_question_fingerprints(command, course)
        expected_validation = _build_validation(
            course,
            existing_count=len(result["existingFingerprints"]),
        )
        if result["questionFingerprints"] != expected_fingerprints:
            raise ValueError("phase 14 question fingerprints are not canonical")
        if any(
            item["fingerprint"] in set(result["existingFingerprints"])
            for item in expected_fingerprints
        ):
            raise ValueError("phase 14 question fingerprints collide")
        if result["validation"] != expected_validation:
            raise ValueError("phase 14 validation is not canonical")
    if (
        command.boundary.get("skillId") == "number_sense_20"
        and command.phase not in {"candidate_repair", "candidate_repair_retry"}
    ):
        _assert_number_sense_representations(result)
    return result


def _normalize_outline_plan(raw: object) -> dict[str, object]:
    value = _plain_mapping(raw, "outlinePlan")
    _require_exact_keys(value, {"courseTitle", "languageDirective", "outlines"}, "outlinePlan")
    outlines = value.get("outlines")
    if not isinstance(outlines, list) or not 1 <= len(outlines) <= 4:
        raise ValueError("outlinePlan.outlines item count is invalid")
    normalized_outlines = []
    for index, raw_outline in enumerate(outlines):
        outline = _plain_mapping(raw_outline, f"outlinePlan.outlines[{index}]")
        _require_exact_keys(outline, {"order", "title", "description", "keyPoints"}, f"outlinePlan.outlines[{index}]")
        if type(outline.get("order")) is not int or outline.get("order") != index + 1:
            raise ValueError("outline order is invalid")
        normalized_outlines.append({
            "order": index + 1,
            "title": _normalized_string(outline.get("title"), "outline.title", maximum=160),
            "description": _normalized_string(outline.get("description"), "outline.description", maximum=500),
            "keyPoints": _normalized_string_array(outline.get("keyPoints"), "outline.keyPoints", maximum=12, string_maximum=300),
        })
    normalized = {
        "courseTitle": _normalized_string(value.get("courseTitle"), "outlinePlan.courseTitle", maximum=160),
        "languageDirective": _normalized_string(value.get("languageDirective"), "outlinePlan.languageDirective", maximum=500),
        "outlines": normalized_outlines,
    }
    if _canonical_json(value) != _canonical_json(normalized):
        raise ValueError("outlinePlan is not canonical")
    return normalized


def _normalize_candidate_projection(
    raw: object,
    command: QuestionPhaseCommand,
    *,
    compiled: bool,
    require_canonical: bool,
    existing_fingerprints: Sequence[str] = (),
) -> dict[str, object]:
    value = _plain_mapping(raw, "checkpoint.candidate")
    projected: dict[str, object] = {}
    for key in ("title", "intro", "estimatedMinutes"):
        if key in value:
            projected[key] = _assert_bounded_json(value[key], f"checkpoint.candidate.{key}")
    raw_flow = value.get("teachingFlow")
    flow: dict[str, object] = {}
    if isinstance(raw_flow, Mapping):
        raw_teach = raw_flow.get("teach")
        if isinstance(raw_teach, Mapping):
            teach = {
                key: _assert_bounded_json(
                    raw_teach[key], f"checkpoint.candidate.teachingFlow.teach.{key}"
                )
                for key in ("title", "sayText", "keyPoints")
                if key in raw_teach
            }
            flow["teach"] = teach
        raw_recap = raw_flow.get("recap")
        if isinstance(raw_recap, Mapping):
            recap = {}
            if "sayText" in raw_recap:
                recap["sayText"] = _assert_bounded_json(
                    raw_recap["sayText"],
                    "checkpoint.candidate.teachingFlow.recap.sayText",
                )
            flow["recap"] = recap
    projected["teachingFlow"] = flow
    raw_questions = value.get("questions")
    questions = []
    if isinstance(raw_questions, list):
        for index, raw_question in enumerate(raw_questions[:10]):
            if not isinstance(raw_question, Mapping):
                questions.append({})
                continue
            question = {
                key: _assert_bounded_json(
                    raw_question[key], f"checkpoint.candidate.questions[{index}].{key}"
                )
                for key in (
                    "type",
                    "prompt",
                    "question",
                    "skill",
                    "hint",
                    "explanation",
                    "answer",
                    "acceptedAnswers",
                    "verificationExpression",
                )
                if key in raw_question
            }
            raw_choices = raw_question.get("choices", raw_question.get("options"))
            if isinstance(raw_choices, list):
                choices = []
                for raw_choice in raw_choices[:8]:
                    if isinstance(raw_choice, (str, int, float)) and not isinstance(raw_choice, bool):
                        choices.append(_assert_bounded_json(raw_choice, "candidate.choice"))
                    elif isinstance(raw_choice, Mapping):
                        choices.append(
                            {
                                key: _assert_bounded_json(
                                    raw_choice[key], f"candidate.choice.{key}"
                                )
                                for key in ("id", "value", "label", "text")
                                if key in raw_choice
                            }
                        )
                question["choices"] = choices
            questions.append(question)
    projected["questions"] = questions
    if require_canonical and _canonical_json(value) != _canonical_json(projected):
        raise ValueError("checkpoint.candidate is not canonical")
    if not compiled:
        return projected
    _require_exact_keys(
        projected,
        {"title", "intro", "estimatedMinutes", "teachingFlow", "questions"},
        "checkpoint.candidate",
    )
    estimated = projected["estimatedMinutes"]
    if type(estimated) is not int or not 5 <= estimated <= 30:
        raise ValueError("candidate estimatedMinutes is invalid")
    normalized_flow = _normalize_generated_teaching_flow(projected["teachingFlow"])
    raw_projected_questions = projected["questions"]
    if not isinstance(raw_projected_questions, list) or len(raw_projected_questions) != 5:
        raise ValueError("compiled candidate must contain five questions")
    normalized_questions = [
        _normalize_compiled_question(
            question,
            index,
            command,
            require_canonical=require_canonical,
        )
        for index, question in enumerate(raw_projected_questions)
    ]
    if normalized_questions[1]["type"] not in {"single_choice", "sequence"}:
        raise ValueError("q2 must use a guided question type")
    if normalized_questions[1]["type"] != normalized_questions[2]["type"]:
        raise ValueError("q2 and q3 must share a guided type")
    if len({_normalized_comparable(item["prompt"]) for item in normalized_questions}) != 5:
        raise ValueError("compiled candidate contains duplicate prompts")
    normalized = {
        "title": _normalized_string(projected["title"], "candidate.title", maximum=160),
        "intro": _normalized_string(projected["intro"], "candidate.intro", maximum=1200),
        "estimatedMinutes": estimated,
        "teachingFlow": normalized_flow,
        "questions": normalized_questions,
    }
    if _practice_leak_indexes(normalized_flow, normalized_questions):
        raise ValueError("compiled candidate teaching flow reveals a practice answer")
    if require_canonical and _canonical_json(projected) != _canonical_json(normalized):
        raise ValueError("compiled candidate is not canonical pure builder output")
    fingerprints = [
        _question_fingerprint(command, question) for question in normalized_questions
    ]
    if len(set(fingerprints)) != len(fingerprints) or any(
        fingerprint in set(existing_fingerprints) for fingerprint in fingerprints
    ):
        raise ValueError("compiled candidate is not original")
    _validate_primary_one_math_blueprint(command, normalized_questions)
    return normalized


def _normalize_generated_teaching_flow(raw: object) -> dict[str, object]:
    value = _plain_mapping(raw, "candidate.teachingFlow")
    _require_exact_keys(value, {"teach", "recap"}, "candidate.teachingFlow")
    teach = _plain_mapping(value.get("teach"), "candidate.teachingFlow.teach")
    recap = _plain_mapping(value.get("recap"), "candidate.teachingFlow.recap")
    _require_exact_keys(teach, {"title", "sayText", "keyPoints"}, "candidate.teachingFlow.teach")
    _require_exact_keys(recap, {"sayText"}, "candidate.teachingFlow.recap")
    return {
        "teach": {
            "title": _normalized_string(teach.get("title"), "teach.title", maximum=160),
            "sayText": _normalized_string(teach.get("sayText"), "teach.sayText", maximum=1200),
            "keyPoints": _normalized_string_array(
                teach.get("keyPoints"), "teach.keyPoints", minimum=1, maximum=3, string_maximum=200
            ),
        },
        "recap": {
            "sayText": _normalized_string(recap.get("sayText"), "recap.sayText", maximum=600)
        },
    }


def _normalize_choice(raw: object, field: str) -> dict[str, str]:
    value = _plain_mapping(raw, field)
    _require_exact_keys(value, {"id", "label"}, field)
    return {
        "id": _normalized_string(value.get("id"), f"{field}.id", maximum=80),
        "label": _normalized_string(value.get("label"), f"{field}.label", maximum=300),
    }


def _normalize_compiled_question(
    raw: object,
    index: int,
    command: QuestionPhaseCommand,
    *,
    allow_choice_prompt_violation: bool = False,
    require_canonical: bool = True,
) -> dict[str, object]:
    field = f"candidate.questions[{index}]"
    value = _plain_mapping(raw, field)
    question_type = _normalized_string(value.get("type"), f"{field}.type", maximum=40)
    type_keys = {
        "numeric": {"type", "prompt", "skill", "hint", "explanation", "answer", "verificationExpression"},
        "single_choice": {"type", "prompt", "skill", "hint", "explanation", "answer", "choices"},
        "exact_text": {"type", "prompt", "skill", "hint", "explanation", "answer"},
        "accepted_text": {"type", "prompt", "skill", "hint", "explanation", "answer", "acceptedAnswers"},
        "sequence": {"type", "prompt", "skill", "hint", "explanation", "answer", "choices"},
    }.get(question_type)
    if type_keys is None:
        raise ValueError(f"{field}.type is invalid")
    _require_exact_keys(value, type_keys, field)
    normalized: dict[str, object] = {
        "type": question_type,
        "prompt": _normalized_string(value.get("prompt"), f"{field}.prompt", maximum=1200),
        "skill": _normalized_string(value.get("skill"), f"{field}.skill", maximum=160),
        "hint": _normalized_string(value.get("hint"), f"{field}.hint", maximum=1000),
        "explanation": _normalized_string(value.get("explanation"), f"{field}.explanation", maximum=1500),
    }
    if normalized["skill"] != command.boundary.get("skillTitle"):
        raise ValueError("question skill changed host authority")
    if question_type == "accepted_text":
        answer = _normalized_string_array(
            value.get("answer"), f"{field}.answer", minimum=1, maximum=6, string_maximum=500
        )
    elif question_type == "sequence":
        answer = _normalized_string_array(
            value.get("answer"), f"{field}.answer", minimum=1, maximum=8, string_maximum=80
        )
    else:
        answer = _normalized_string(value.get("answer"), f"{field}.answer", maximum=500)
    normalized["answer"] = answer
    if question_type == "numeric":
        expression = _normalize_arithmetic_expression(value.get("verificationExpression"), field)
        _assert_numeric_answer(str(answer), expression, field)
        normalized["verificationExpression"] = expression
    if question_type == "accepted_text":
        accepted = _normalized_string_array(
            value.get("acceptedAnswers"), f"{field}.acceptedAnswers", minimum=1, maximum=6, string_maximum=500
        )
        if accepted != answer:
            raise ValueError("accepted_text answer authority differs")
        _assert_unique_accepted_text_answers(
            answer, command.subject, f"{field}.answer"
        )
        normalized["acceptedAnswers"] = accepted
    if question_type in {"single_choice", "sequence"}:
        raw_choices = value.get("choices")
        if not isinstance(raw_choices, list) or not 2 <= len(raw_choices) <= 8:
            raise ValueError("question choices are invalid")
        choices = [
            _normalize_choice(choice, f"{field}.choices[{choice_index}]")
            for choice_index, choice in enumerate(raw_choices)
        ]
        ids = [choice["id"] for choice in choices]
        labels = [choice["label"] for choice in choices]
        if len(set(map(_normalized_comparable, ids))) != len(ids) or len(
            set(map(_normalized_comparable, labels))
        ) != len(labels):
            raise ValueError("question choices contain duplicates")
        if question_type == "single_choice" and answer not in ids:
            raise ValueError("single choice answer is not a choice id")
        if question_type == "sequence" and (
            len(answer) != len(ids) or len(set(answer)) != len(answer) or any(item not in ids for item in answer)
        ):
            raise ValueError("sequence answer must order every choice")
        if question_type == "sequence" and answer == ids:
            choices = list(reversed(choices))
        normalized["choices"] = choices
    _assert_question_does_not_reveal(
        normalized,
        allow_choice_prompt_violation=allow_choice_prompt_violation,
    )
    if require_canonical and _canonical_json(value) != _canonical_json(normalized):
        raise ValueError("compiled question is not canonical")
    return normalized


def _normalize_lesson_text(raw: object) -> dict[str, object]:
    value = _plain_mapping(raw, "checkpoint.lessonText")
    _require_exact_keys(value, {"title", "intro", "teachingFlow"}, "checkpoint.lessonText")
    normalized = {
        "title": _normalized_string(value.get("title"), "lessonText.title", maximum=160),
        "intro": _normalized_string(value.get("intro"), "lessonText.intro", maximum=1200),
        "teachingFlow": _normalize_generated_teaching_flow(value.get("teachingFlow")),
    }
    if _canonical_json(value) != _canonical_json(normalized):
        raise ValueError("checkpoint.lessonText is not canonical")
    return normalized


def _normalize_reconciliation(
    raw: object,
    command: QuestionPhaseCommand,
    *,
    existing_fingerprints: Sequence[str],
) -> dict[str, object]:
    value = _plain_mapping(raw, "checkpoint.reconciliation")
    _require_exact_keys(value, {"estimatedMinutes", "questions"}, "checkpoint.reconciliation")
    estimated = value.get("estimatedMinutes")
    if type(estimated) is not int or not 5 <= estimated <= 30:
        raise ValueError("reconciliation estimatedMinutes is invalid")
    raw_questions = value.get("questions")
    if not isinstance(raw_questions, list) or len(raw_questions) != 5:
        raise ValueError("reconciliation must contain five questions")
    questions = [
        _normalize_compiled_question(
            question,
            index,
            command,
            allow_choice_prompt_violation=True,
        )
        for index, question in enumerate(raw_questions)
    ]
    if questions[1]["type"] not in {"single_choice", "sequence"} or questions[1]["type"] != questions[2]["type"]:
        raise ValueError("reconciliation guided question types are invalid")
    fingerprints = [_question_fingerprint(command, question) for question in questions]
    if len(set(fingerprints)) != len(fingerprints) or any(
        fingerprint in set(existing_fingerprints) for fingerprint in fingerprints
    ):
        raise ValueError("reconciliation is not original")
    _validate_primary_one_math_blueprint(command, questions)
    normalized = {"estimatedMinutes": estimated, "questions": questions}
    if _canonical_json(value) != _canonical_json(normalized):
        raise ValueError("reconciliation is not canonical")
    return normalized


def _normalize_question_indexes(raw: object, field: str) -> list[int]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= 4:
        raise ValueError(f"{field} must contain one to four indexes")
    if any(type(item) is not int or not 1 <= item <= 4 for item in raw):
        raise ValueError(f"{field} contains an invalid index")
    if raw != sorted(set(raw)):
        raise ValueError(f"{field} must be strictly ascending")
    return list(raw)


def _normalize_prior_rejection(phase: str, raw: object) -> str:
    allowed = {
        "candidate_repair_retry": {"candidate_repair_schema_rejected", "candidate_repair_originality_rejected"},
        "reconciliation_retry": {"reconciliation_schema_rejected", "reconciliation_originality_rejected"},
        "consistency_repair_retry": {"consistency_repair_schema_rejected"},
    }.get(phase, set())
    if raw not in allowed:
        raise ValueError("priorRejectionCode does not match preceding phase")
    return str(raw)


_NORMALIZATION_BY_TYPE = {
    "numeric": ["trim", "remove_grouping_separators"],
    "single_choice": ["trim", "casefold"],
    "sequence": ["trim", "casefold"],
    "exact_text": ["trim", "collapse_whitespace"],
    "accepted_text": ["trim", "collapse_whitespace"],
}
_SAFE_QUESTION_TYPES = frozenset(_NORMALIZATION_BY_TYPE)
_GUIDED_QUESTION_TYPES = frozenset({"single_choice", "sequence"})


def _normalization_for(question_type: str, subject: str) -> list[str]:
    result = list(_NORMALIZATION_BY_TYPE[question_type])
    if question_type in {"exact_text", "accepted_text"}:
        if subject == "english":
            result.extend(("casefold", "strip_terminal_punctuation"))
        else:
            result.append("remove_whitespace")
    return result


def _is_scoring_whitespace(character: str) -> bool:
    return character.isspace() or character in "\u001c\u001d\u001e\u001f"


def _assert_accepted_text_scoring_domain(
    values: Sequence[str], subject: str, field: str
) -> None:
    for index, value in enumerate(values):
        normalized = unicodedata.normalize("NFKC", value)
        for character in normalized:
            category = unicodedata.category(character)
            if (
                category in {"Cc", "Cf"}
                and not _is_scoring_whitespace(character)
            ) or (
                subject == "english"
                and category.startswith("L")
                and not re.fullmatch(r"[A-Za-z]", character)
            ):
                raise ValueError(
                    f"{field}[{index}] is outside the canonical scoring text domain"
                )


def _strip_scoring_edge_whitespace(value: str) -> str:
    start = 0
    end = len(value)
    while start < end and _is_scoring_whitespace(value[start]):
        start += 1
    while end > start and _is_scoring_whitespace(value[end - 1]):
        end -= 1
    return value[start:end]


def _replace_scoring_whitespace(value: str, replacement: str) -> str:
    parts: list[str] = []
    in_run = False
    for character in value:
        if _is_scoring_whitespace(character):
            if replacement and not in_run:
                parts.append(replacement)
            in_run = True
        else:
            parts.append(character)
            in_run = False
    return "".join(parts)


def _normalized_evaluation_comparable(
    value: object, operations: Sequence[str]
) -> str:
    normalized = unicodedata.normalize("NFKC", str(value))
    for operation in operations:
        if operation == "trim":
            normalized = _strip_scoring_edge_whitespace(normalized)
        elif operation == "collapse_whitespace":
            normalized = _replace_scoring_whitespace(normalized, " ")
        elif operation == "remove_whitespace":
            normalized = _replace_scoring_whitespace(normalized, "")
        elif operation == "casefold":
            normalized = normalized.casefold()
        elif operation == "strip_terminal_punctuation":
            normalized = re.sub(r"[.!?;:。！？；：]+$", "", normalized)
            normalized = _strip_scoring_edge_whitespace(normalized)
        elif operation == "remove_grouping_separators":
            normalized = normalized.replace(",", "")
    return normalized


def _assert_unique_accepted_text_answers(
    values: Sequence[str], subject: str, field: str
) -> None:
    _assert_accepted_text_scoring_domain(values, subject, field)
    normalization = _normalization_for("accepted_text", subject)
    comparable = [_normalized_comparable(value) for value in values]
    scoring = [
        _normalized_evaluation_comparable(value, normalization) for value in values
    ]
    if len(set(comparable)) != len(values) or len(set(scoring)) != len(values):
        raise ValueError(f"{field} contains equivalent answers")


def _normalized_comparable(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value))
    normalized = re.sub(
        r"[\u0009-\u000D\u0020\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000\uFEFF]+",
        " ",
        normalized,
    )
    return normalized.strip().lower()


def _normalize_arithmetic_expression(value: object, field: str) -> str:
    expression = _normalized_string(value, f"{field}.verificationExpression", maximum=128)
    expression = expression.replace("×", "*").replace("÷", "/")
    if not re.fullmatch(r"[0-9+\-*/().\s]+", expression):
        raise ValueError(f"{field}.verificationExpression contains unsupported arithmetic")
    return re.sub(r"\s+", "", expression)


def _evaluate_arithmetic(expression: str) -> float:
    parsed = ast.parse(expression, mode="eval")

    def evaluate(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = float(node.value)
            if not math.isfinite(value):
                raise ValueError("arithmetic value is not finite")
            return value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)
        ):
            left = evaluate(node.left)
            right = evaluate(node.right)
            if isinstance(node.op, ast.Add):
                result = left + right
            elif isinstance(node.op, ast.Sub):
                result = left - right
            elif isinstance(node.op, ast.Mult):
                result = left * right
            else:
                result = left / right
            if not math.isfinite(result):
                raise ValueError("arithmetic result is not finite")
            return result
        raise ValueError("unsupported arithmetic node")

    return evaluate(parsed)


def _assert_numeric_answer(answer: str, expression: str, field: str) -> None:
    try:
        expected = float(answer.replace(",", ""))
        calculated = _evaluate_arithmetic(expression)
    except (TypeError, ValueError, ZeroDivisionError, SyntaxError) as exc:
        raise ValueError(f"{field} numeric authority is invalid") from exc
    if not math.isfinite(expected):
        raise ValueError(f"{field}.answer must be a decimal number")
    tolerance = max(1.0, abs(expected), abs(calculated)) * 1e-10
    if abs(expected - calculated) > tolerance:
        raise ValueError(f"{field}.verificationExpression does not yield the answer")


def _question_fingerprint(
    command: QuestionPhaseCommand, question: Mapping[str, object]
) -> str:
    return DynamicLearningCourseRepository.question_fingerprint(
        grade_code=command.grade_code,
        subject=command.subject,
        node_code=str(command.boundary.get("skillId") or ""),
        question=question,
    )


def _question_public_text(question: Mapping[str, object]) -> str:
    labels = [
        str(choice.get("label") or "")
        for choice in question.get("choices", [])
        if isinstance(choice, Mapping)
    ]
    values = [
        question.get("prompt"),
        question.get("hint"),
        question.get("explanation"),
        *labels,
    ]
    return " ".join(unicodedata.normalize("NFKC", str(item or "")) for item in values)


def _correct_choice_label(question: Mapping[str, object]) -> str:
    answer = str(question.get("answer") or "")
    for choice in question.get("choices", []):
        if isinstance(choice, Mapping) and str(choice.get("id") or "") == answer:
            return unicodedata.normalize("NFKC", str(choice.get("label") or ""))
    return ""


def _number_sense_kind(question: Mapping[str, object]) -> str:
    prompt = unicodedata.normalize("NFKC", str(question.get("prompt") or ""))
    if re.search(r"组成|几个十|几个一|十位|个位", prompt):
        return "composition"
    if re.search(r"比较|大小|更多|更少|大于|小于|[<>]", prompt):
        return "comparison"
    return "other"


def _number_sense_adjacent_answer_is_recomputable(
    question: Mapping[str, object],
) -> bool:
    if question.get("type") != "single_choice":
        return False
    raw_choices = question.get("choices")
    if not isinstance(raw_choices, list) or len(raw_choices) < 2:
        return False
    choice_values: list[int] = []
    for choice in raw_choices:
        if not isinstance(choice, Mapping):
            return False
        label = unicodedata.normalize(
            "NFKC", str(choice.get("label") or "")
        ).strip()
        if re.fullmatch(r"(?:0|[1-9]\d?)", label) is None:
            return False
        value = int(label)
        if not 0 <= value <= 20:
            return False
        choice_values.append(value)
    if len(set(choice_values)) != len(choice_values):
        return False

    selected = _correct_choice_label(question).strip()
    if re.fullmatch(r"(?:0|[1-9]\d?)", selected) is None:
        return False
    selected_value = int(selected)
    if not 0 <= selected_value <= 20 or choice_values.count(selected_value) != 1:
        return False

    prompt = unicodedata.normalize(
        "NFKC", str(question.get("prompt") or question.get("question") or "")
    )
    calculation_prompt = re.sub(r"(?<!\d)20\s*以内", "", prompt)
    prompt_values = [
        int(match.group(1))
        for match in re.finditer(r"(?<!\d)(\d{1,4})(?!\d)", calculation_prompt)
    ]
    if any(value < 0 or value > 20 for value in prompt_values):
        return False
    expected: list[int] = []
    directional = re.search(
        r"从\s*(\d{1,2})\s*(往后|向后|往前|向前)\s*(?:数)?[^.。?!？！]{0,24}?(?:紧接着|下一个|上一个|前一个|后一个)",
        prompt,
    )
    if directional is not None:
        anchor = int(directional.group(1))
        expected.append(
            anchor + (1 if directional.group(2) in {"往后", "向后"} else -1)
        )
    direct_ordinal = re.search(
        r"(?<!\d)(\d{1,2})(?!\d)\s*(?:的)?\s*(前一个|后一个)\s*(?:数)?",
        prompt,
    )
    if direct_ordinal is not None:
        anchor = int(direct_ordinal.group(1))
        expected.append(anchor + (1 if direct_ordinal.group(2) == "后一个" else -1))
    direct_adjacent = re.search(
        r"(?<!\d)(\d{1,2})(?!\d)\s*(?:的)?\s*(前面|后面)\s*(?:的)?\s*(?:紧接着|紧挨着|相邻)\s*(?:的)?\s*(?:一个)?\s*(?:数)?",
        prompt,
    )
    if direct_adjacent is not None:
        anchor = int(direct_adjacent.group(1))
        expected.append(anchor + (1 if direct_adjacent.group(2) == "后面" else -1))
    blank = re.search(
        r"(?<!\d)(\d{1,2})(?!\d)\s*[、,]\s*(?:□|_{1,4}|\?|\(\s*\))\s*[、,]\s*(\d{1,2})(?!\d)",
        prompt,
    )
    if blank is not None:
        left, right = int(blank.group(1)), int(blank.group(2))
        if abs(left - right) == 2:
            expected.append(min(left, right) + 1)
    valid = set(expected)
    return (
        len(valid) == 1
        and all(0 <= value <= 20 for value in valid)
        and selected_value in valid
    )


def _previous_non_python_whitespace_index(text: str, start: int) -> int:
    index = start - 1
    while index >= 0 and text[index].isspace():
        index -= 1
    return index


def _next_non_python_whitespace_index(text: str, start: int) -> int:
    index = start
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _is_han_character(character: str) -> bool:
    return len(character) == 1 and "\u3400" <= character <= "\u9fff"


def _number_token_has_left_boundary(text: str, token_start: int) -> bool:
    index = _previous_non_python_whitespace_index(text, token_start)
    if index < 0:
        return True
    character = text[index]
    if _is_han_character(character):
        return character not in {"负", "几"}
    if character in "。！？；、([{\"'“‘【":
        return True
    if character not in ",;:":
        return False
    before_punctuation = _previous_non_python_whitespace_index(text, index)
    return before_punctuation >= 0 and _is_han_character(text[before_punctuation])


def _is_canonical_unsigned_integer_text(value: str) -> bool:
    return re.fullmatch(r"(?:0|[1-9][0-9]*)", value) is not None


_MAX_SAFE_UNSIGNED_INTEGER_TEXT = "9007199254740991"


def _is_safe_unsigned_integer_text(value: str) -> bool:
    return len(value) < len(_MAX_SAFE_UNSIGNED_INTEGER_TEXT) or (
        len(value) == len(_MAX_SAFE_UNSIGNED_INTEGER_TEXT)
        and value <= _MAX_SAFE_UNSIGNED_INTEGER_TEXT
    )


def _read_canonical_unsigned_before_unit(
    text: str, unit_index: int
) -> dict[str, object]:
    end = unit_index
    while end > 0 and text[end - 1].isspace():
        end -= 1
    start = end
    while start > 0 and "0" <= text[start - 1] <= "9":
        start -= 1
    if start == end:
        placeholder_index = _previous_non_python_whitespace_index(text, end)
        if placeholder_index >= 0 and text[placeholder_index] == "几":
            return {"kind": "placeholder", "start": placeholder_index}
        return {"kind": "malformed"}
    raw = text[start:end]
    if (
        not _is_canonical_unsigned_integer_text(raw)
        or not _is_safe_unsigned_integer_text(raw)
        or not _number_token_has_left_boundary(text, start)
    ):
        return {"kind": "malformed"}
    return {"kind": "number", "value": int(raw), "start": start}


def _read_canonical_unsigned_after(text: str, start: int) -> dict[str, object]:
    index = _next_non_python_whitespace_index(text, start)
    token_start = index
    while index < len(text) and "0" <= text[index] <= "9":
        index += 1
    if index == token_start:
        return {"kind": "malformed"}
    raw = text[token_start:index]
    if not _is_canonical_unsigned_integer_text(
        raw
    ) or not _is_safe_unsigned_integer_text(raw):
        return {"kind": "malformed"}
    return {"kind": "number", "value": int(raw), "end": index}


def _next_unit_phrase_boundary_index(text: str, start: int) -> int:
    for index in range(start, len(text)):
        if text[index] in "。！？!?；;,":
            return index
    return len(text)


def _has_invalid_right_numeric_continuation(text: str, start: int) -> bool:
    index = _next_non_python_whitespace_index(text, start)
    if index >= len(text):
        return False
    character = text[index]
    if character in "_+-−负./*×÷∕" or character.isascii() and character.isalnum():
        return True
    return (
        text.startswith("个十", index)
        or text.startswith("个一", index)
        or character == "和"
    )


_NUMBER_SENSE_COMPOSITION_STRONG_CONTEXT_DELIMITERS = frozenset(
    "。!?！？;；"
)
_NUMBER_SENSE_COMPOSITION_CLAUSE_DELIMITERS = frozenset(
    ",，:：.。!?！？;；、"
)
_NUMBER_SENSE_COMPOSITION_BACKGROUND_TEMPLATES = (
    ("果篮里有", "个水果"),
    ("果篮里有", "个果子"),
    ("企鹅画家有", "支画笔"),
    ("贴纸上的数字是", ""),
    ("果篮上标着数字", ""),
    ("小云雀的贝壳收藏架上标着数字", ""),
    ("小兔子的篮子里有", "个胡萝卜"),
    ("车票上写着", "号"),
    ("地上有", "颗石子"),
    ("上面写着数字", ""),
    ("车票上的数字是", ""),
    ("小水獭用石子摆出了数字", ""),
    ("车身上写着数字", ""),
    ("礼物盒上写着数字", ""),
    ("一共有", "张邮票"),
    ("有一张卡片上写着", ""),
    ("有一张卡片上写着数字", ""),
    ("上面标着数字", ""),
    ("小熊猫的果篮里正好装了", "个果子"),
    ("齿轮零件盒上写着数字", ""),
    ("它看到齿轮上标着数字", ""),
    ("车票上写着数字", ""),
    ("小车上的数字牌写着", ""),
    ("彩旗上写着数字", ""),
    ("小考拉的篮子里装了", "个月亮果"),
    ("贴纸摊位有", "张贴纸"),
    ("小象的礼物盒上写着数字", ""),
    ("看到一张写着数字", "的星星卡"),
    ("小猫书签上写着数字", ""),
    ("其中一张星星卡上写着数字", ""),
    ("星光邮局的花盆标签上写着数字", ""),
    ("有一个花盆上写着", ""),
    ("写着", ""),
    ("上面画着数字", ""),
    ("卡片上写着数字", ""),
    ("小刺猬有", "颗石子"),
    ("盒子装了", "个积木"),
    ("小猫钓到了", "条鱼"),
    ("拼板一共是", "块"),
    ("卡片写着", ""),
    ("卡片写着", "号"),
    ("卡片写着数字", ""),
    ("卡片的数字是", ""),
    ("小狐狸有一张写着数字", "的星星卡"),
    ("小狐狸有一张写着数字", "的车票"),
    ("它已经贴好了", "张贴纸"),
)
_NUMBER_SENSE_COMPOSITION_CHINESE_NUMERAL_PATTERN = re.compile(
    r"[零〇一二三四五六七八九十拾百佰千仟万萬亿億兆廿卅卌两兩壹贰貳叁參肆伍陆陸柒捌玖]+"
)
_NUMBER_SENSE_COMPOSITION_PAIRED_CUE_PATTERN = re.compile(
    r"几个十 *(?:和|与|、) *几个一"
)
_NUMBER_SENSE_COMPOSITION_FULL_QUESTION_PATTERN = re.compile(
    r"(?<![0-9])([0-9]{1,2})(?![0-9]) *(?:(?:这个|该)(?:数|数字) *)?"
    r"(?:(是由|由) *几个十 *(?:和|与|、) *几个一 *组成(?:的)?"
    r"|(里面有) *几个十 *(?:和|与|、) *几个一) *[？?]"
)


def _number_sense_composition_target_occurrence_has_allowed_left_context(
    text: str, token_start: int
) -> bool:
    prefix = text[:token_start].strip(" ")
    if not prefix:
        return True
    if prefix[-1] in _NUMBER_SENSE_COMPOSITION_STRONG_CONTEXT_DELIMITERS:
        return True
    last_delimiter_index = max(
        (
            index
            for index, character in enumerate(prefix)
            if character in _NUMBER_SENSE_COMPOSITION_STRONG_CONTEXT_DELIMITERS
        ),
        default=-1,
    )
    segment = prefix[last_delimiter_index + 1 :].strip(" ")
    return re.fullmatch(
        r"(?:数字|(?:请问|那么|其中) *[:：,，]?|小云雀想知道[:：])",
        segment,
    ) is not None


def _number_sense_composition_clause_bounds(
    text: str, token_start: int, token_end: int
) -> tuple[int, int]:
    start = 0
    for index in range(token_start - 1, -1, -1):
        if text[index] in _NUMBER_SENSE_COMPOSITION_CLAUSE_DELIMITERS:
            start = index + 1
            break
    end = len(text)
    for index in range(token_end, len(text)):
        if text[index] in _NUMBER_SENSE_COMPOSITION_CLAUSE_DELIMITERS:
            end = index
            break
    return start, end


def _number_sense_composition_background_occurrence_has_allowed_role(
    text: str, token_start: int, token_end: int
) -> bool:
    clause_start, clause_end = _number_sense_composition_clause_bounds(
        text, token_start, token_end
    )
    raw_clause = text[clause_start:clause_end]
    leading_length = len(raw_clause) - len(raw_clause.lstrip(" "))
    clause = raw_clause.strip(" ")
    relative_start = token_start - clause_start - leading_length
    relative_end = token_end - clause_start - leading_length
    token = text[token_start:token_end]
    return any(
        clause == f"{prefix}{token}{suffix}"
        and relative_start == len(prefix)
        and relative_end == len(prefix) + len(token)
        for prefix, suffix in _NUMBER_SENSE_COMPOSITION_BACKGROUND_TEMPLATES
    )


def _number_sense_composition_target_has_invalid_right_continuation(
    text: str, start: int
) -> bool:
    index = _next_non_python_whitespace_index(text, start)
    return _has_invalid_right_numeric_continuation(text, start) or (
        index < len(text) and text[index] in {"%", "点"}
    )


def _number_sense_composition_raw_numeric_characters_are_allowed(text: str) -> bool:
    for character in text:
        allowed_raw_digit = "0" <= character <= "9" or "０" <= character <= "９"
        normalized_contains_ascii_digit = any(
            "0" <= normalized_character <= "9"
            for normalized_character in unicodedata.normalize("NFKC", character)
        )
        category = unicodedata.category(character)
        is_decimal_number = category == "Nd"
        if not allowed_raw_digit and (
            normalized_contains_ascii_digit
            or is_decimal_number
            or category in {"Nl", "No"}
        ):
            return False
    return True


def _normalize_number_sense_composition_python_whitespace(text: str) -> str:
    mapped = "".join(" " if character.isspace() else character for character in text)
    return re.sub(r" +", " ", mapped)


def _number_sense_composition_has_chinese_numeral_in_numeric_role(
    text: str,
) -> bool:
    for match in _NUMBER_SENSE_COMPOSITION_CHINESE_NUMERAL_PATTERN.finditer(text):
        if _number_sense_composition_background_occurrence_has_allowed_role(
            text, match.start(), match.end()
        ):
            return True
        suffix = text[match.end() :]
        if (
            _number_sense_composition_target_occurrence_has_allowed_left_context(
                text, match.start()
            )
            and re.match(
                r"^(?: *(?:(?:这个|该)(?:数|数字) *)?"
                r"(?:(?:是由|由) *几个十 *(?:和|与|、) *几个一 *组成(?:的)?"
                r"|里面有 *几个十 *(?:和|与|、) *几个一) *[？?])",
                suffix,
            )
        ):
            return True
    return False


def _number_sense_composition_raw_prompt_is_allowed(raw_prompt: str) -> bool:
    if not _number_sense_composition_raw_numeric_characters_are_allowed(raw_prompt):
        return False
    if any(
        character in raw_prompt
        for character in "\u000A\u000B\u000C\u000D\u0085\u2028\u2029\uFEFF"
    ):
        return False
    normalized = _normalize_number_sense_composition_python_whitespace(
        unicodedata.normalize("NFKC", raw_prompt)
    )
    return not _number_sense_composition_has_chinese_numeral_in_numeric_role(
        normalized
    )


def _parse_number_sense_composition_prompt(
    question: Mapping[str, object], *, require_from_composition: bool = False
) -> dict[str, object] | None:
    if question.get("type") != "single_choice":
        return None
    raw_prompt = str(question.get("prompt") or question.get("question") or "")
    if not _number_sense_composition_raw_prompt_is_allowed(raw_prompt):
        return None
    prompt = _normalize_number_sense_composition_python_whitespace(
        unicodedata.normalize("NFKC", raw_prompt)
    )
    tens_cues = list(re.finditer(r"几个十", prompt))
    ones_cues = list(re.finditer(r"几个一", prompt))
    paired_cues = list(
        _NUMBER_SENSE_COMPOSITION_PAIRED_CUE_PATTERN.finditer(prompt)
    )
    semantic_matches = list(
        _NUMBER_SENSE_COMPOSITION_FULL_QUESTION_PATTERN.finditer(prompt)
    )
    if (
        len(tens_cues) != 1
        or len(ones_cues) != 1
        or len(paired_cues) != 1
        or len(semantic_matches) != 1
    ):
        return None
    semantic_match = semantic_matches[0]
    paired_cue = paired_cues[0]
    if not (
        semantic_match.start() <= paired_cue.start()
        and paired_cue.end() <= semantic_match.end()
    ):
        return None
    semantic_kind = "from" if semantic_match.group(2) else "inside"
    if require_from_composition and semantic_kind != "from":
        return None
    target_token_start = semantic_match.start(1)
    target_token_end = semantic_match.end(1)
    if not _number_sense_composition_target_occurrence_has_allowed_left_context(
        prompt, target_token_start
    ):
        return None
    numeric_tokens = list(re.finditer(r"[0-9]+", prompt))
    if not numeric_tokens:
        return None
    numeric_values: list[int] = []
    for token in numeric_tokens:
        raw = token.group(0)
        value = int(raw)
        if (
            not _is_canonical_unsigned_integer_text(raw)
            or not _is_safe_unsigned_integer_text(raw)
            or not 0 <= value <= 20
            or _number_sense_composition_target_has_invalid_right_continuation(
                prompt, token.end()
            )
        ):
            return None
        numeric_values.append(value)
    distinct_values = set(numeric_values)
    if len(distinct_values) != 1:
        return None
    target = int(semantic_match.group(1))
    if target not in distinct_values:
        return None
    for token in numeric_tokens:
        if token.start() == target_token_start and token.end() == target_token_end:
            continue
        if not _number_sense_composition_background_occurrence_has_allowed_role(
            prompt, token.start(), token.end()
        ):
            return None
    return {
        "prompt": prompt,
        "target": target,
        "semantic_kind": semantic_kind,
        "semantic_start": semantic_match.start(),
        "semantic_end": semantic_match.end(),
        "target_token_start": target_token_start,
        "target_token_end": target_token_end,
    }


def _number_sense_composition_prompt_target(
    question: Mapping[str, object], *, require_from_composition: bool = False
) -> int | None:
    parsed = _parse_number_sense_composition_prompt(
        question, require_from_composition=require_from_composition
    )
    return int(parsed["target"]) if parsed is not None else None


_UNIT_LIKE_NUMERAL_CHARACTERS = frozenset(
    "0123456789几零〇一二三四五六七八九两兩壹贰貳叁參肆伍陆陸柒捌玖廿卅卌"
)
_UNIT_LIKE_PLACE_VALUE_CHARACTERS = frozenset("十拾百佰千仟万萬亿億兆")
_UNIT_LIKE_COMPONENT_CHARACTERS = (
    _UNIT_LIKE_NUMERAL_CHARACTERS
    | _UNIT_LIKE_PLACE_VALUE_CHARACTERS
    | frozenset("个位")
)


def _immediate_unit_like_component_before_connector(
    text: str, connector_index: int
) -> tuple[str, int] | None:
    left_end = _previous_non_python_whitespace_index(text, connector_index)
    if (
        left_end < 0
        or text[left_end] not in _UNIT_LIKE_COMPONENT_CHARACTERS
    ):
        return None
    reversed_characters: list[str] = []
    start = left_end
    for index in range(left_end, -1, -1):
        character = text[index]
        if character.isspace():
            continue
        if character not in _UNIT_LIKE_COMPONENT_CHARACTERS:
            break
        reversed_characters.append(character)
        start = index
    return "".join(reversed(reversed_characters)), start


def _has_immediate_malformed_tens_component(
    text: str, connector_index: int
) -> bool:
    left_end = _previous_non_python_whitespace_index(text, connector_index)
    if left_end < 0:
        return True
    immediate_component = _immediate_unit_like_component_before_connector(
        text, connector_index
    )
    if immediate_component is None:
        return False
    component, component_start = immediate_component
    if re.fullmatch(r"(?:[0-9]+|几)", component) is not None:
        return True
    if re.fullmatch(r"(?:[0-9]+|几)个十", component) is not None:
        return False
    if component.endswith("位"):
        stem = component[:-1]
        if "个" in stem:
            return True
        ordinal_prefix_index = _previous_non_python_whitespace_index(
            text, component_start
        )
        if (
            ordinal_prefix_index >= 0
            and text[ordinal_prefix_index] == "第"
        ):
            return False
        return any(
            character in _UNIT_LIKE_PLACE_VALUE_CHARACTERS
            for character in stem
        )
    return any(
        character in _UNIT_LIKE_PLACE_VALUE_CHARACTERS
        for character in component
    )


def _has_malformed_attempted_pair(text: str) -> bool:
    search_index = 0
    while search_index < len(text):
        ones_unit_index = text.find("个一", search_index)
        if ones_unit_index < 0:
            return False
        token_end = ones_unit_index
        while token_end > 0 and text[token_end - 1].isspace():
            token_end -= 1
        token_start = token_end
        while token_start > 0 and "0" <= text[token_start - 1] <= "9":
            token_start -= 1
        if token_start == token_end:
            placeholder_index = _previous_non_python_whitespace_index(
                text, token_end
            )
            if placeholder_index < 0 or text[placeholder_index] != "几":
                search_index = ones_unit_index + len("个一")
                continue
            token_start = placeholder_index
        connector_index = _previous_non_python_whitespace_index(text, token_start)
        if connector_index < 0 or text[connector_index] != "和":
            search_index = ones_unit_index + len("个一")
            continue
        if not _has_immediate_malformed_tens_component(text, connector_index):
            search_index = ones_unit_index + len("个一")
            continue
        return True
    return False


def _malformed_number_sense_classification() -> dict[str, object]:
    return {"status": "malformed", "representations": []}


def _is_canonical_number_sense_representation(tens: int, ones: int) -> bool:
    return (tens in {0, 1} and 0 <= ones <= 9) or (tens == 2 and ones == 0)


def classify_number_sense_unit_phrases(value: str) -> dict[str, object]:
    """Classify the sealed Grade-1 tens-and-ones phrase grammar."""

    if not isinstance(value, str):
        raise TypeError("number-sense phrase must be a string")
    text = unicodedata.normalize("NFKC", value)
    representations: list[dict[str, object]] = []
    semantic_violation = False
    search_index = 0

    if _has_malformed_attempted_pair(text):
        return _malformed_number_sense_classification()

    while search_index < len(text):
        tens_unit_index = text.find("个十", search_index)
        if tens_unit_index < 0:
            break
        tens_token = _read_canonical_unsigned_before_unit(text, tens_unit_index)
        tens_unit_end = tens_unit_index + len("个十")
        if tens_token["kind"] == "malformed":
            return _malformed_number_sense_classification()

        cursor = _next_non_python_whitespace_index(text, tens_unit_end)
        if tens_token["kind"] == "placeholder":
            if cursor >= len(text) or text[cursor] != "和":
                return _malformed_number_sense_classification()
            cursor = _next_non_python_whitespace_index(text, cursor + 1)
            if cursor >= len(text) or text[cursor] != "几":
                return _malformed_number_sense_classification()
            cursor = _next_non_python_whitespace_index(text, cursor + 1)
            if not text.startswith("个一", cursor):
                return _malformed_number_sense_classification()
            cursor += len("个一")
            if _has_invalid_right_numeric_continuation(text, cursor):
                return _malformed_number_sense_classification()
            search_index = cursor
            continue

        kind = "tens-only"
        ones = 0
        if cursor < len(text) and text[cursor] == "和":
            ones_token = _read_canonical_unsigned_after(text, cursor + 1)
            if ones_token["kind"] != "number":
                return _malformed_number_sense_classification()
            cursor = _next_non_python_whitespace_index(text, int(ones_token["end"]))
            if not text.startswith("个一", cursor):
                return _malformed_number_sense_classification()
            cursor += len("个一")
            if _has_invalid_right_numeric_continuation(text, cursor):
                return _malformed_number_sense_classification()
            kind = "pair"
            ones = int(ones_token["value"])
        else:
            boundary = _next_unit_phrase_boundary_index(text, cursor)
            if "个一" in text[cursor:boundary] or _has_invalid_right_numeric_continuation(
                text, cursor
            ):
                return _malformed_number_sense_classification()
            cursor = tens_unit_end

        tens = int(tens_token["value"])
        representation = {"kind": kind, "tens": tens, "ones": ones}
        representations.append(representation)
        if not _is_canonical_number_sense_representation(tens, ones):
            semantic_violation = True
        search_index = max(cursor, tens_unit_end)

    if not representations:
        return {"status": "not-representation", "representations": []}
    return {
        "status": "malformed" if semantic_violation else "valid",
        "representations": representations,
    }


_NUMBER_SENSE_GENERIC_TEACHING_PATTERNS = (
    re.compile(r"(?<![0-9])1\s*个十\s*和\s*几个一(?![0-9])"),
    re.compile(
        r"(?:有\s*)?几个十\s*"
        r"(?:和|[/,、;]\s*(?:(?:再\s*)?看\s*)?|再\s*看\s*)"
        r"(?:有\s*)?几个一"
    ),
)


def _project_number_sense_teaching_text(value: str) -> str:
    projected = unicodedata.normalize("NFKC", value)
    for pattern in _NUMBER_SENSE_GENERIC_TEACHING_PATTERNS:
        projected = pattern.sub("十与一的泛化组成", projected)
    projected = re.sub(r"(?<!第)几个十", "十位数量", projected)
    return re.sub(r"(?<!第)几个一", "个位数量", projected)


def _is_number_sense_teaching_text_path(
    path: tuple[object, ...],
    *,
    teaching_root_keys: frozenset[str],
) -> bool:
    if path and path[0] in teaching_root_keys:
        return True
    return any(
        path[index] in {"teachingFlow", "repair"}
        and path[index + 1] in {"teach", "recap"}
        for index in range(len(path) - 1)
    )


def _assert_number_sense_representations(
    value: object,
    *,
    teaching_root_keys: frozenset[str] = frozenset(),
) -> None:
    strings: list[tuple[str, bool]] = []

    def visit(item: object, path: tuple[object, ...]) -> None:
        if isinstance(item, str):
            strings.append(
                (
                    unicodedata.normalize("NFKC", item),
                    _is_number_sense_teaching_text_path(
                        path,
                        teaching_root_keys=teaching_root_keys,
                    ),
                )
            )
        elif isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, (*path, index))
        elif isinstance(item, Mapping):
            for key, child in item.items():
                visit(child, (*path, key))

    visit(value, ())
    for text, is_teaching_text in strings:
        standalone_question_placeholders = re.sub(
            r"(?<!第)几个十(?=\s*(?:[？?]|$))",
            "十位数量",
            text,
        )
        classified_text = (
            _project_number_sense_teaching_text(standalone_question_placeholders)
            if is_teaching_text
            else standalone_question_placeholders
        )
        classification = classify_number_sense_unit_phrases(classified_text)
        for representation in classification["representations"]:
            tens = int(representation["tens"])
            ones = int(representation["ones"])
            if tens * 10 + ones > 20:
                raise ValueError(
                    "number_sense_20 contains an out-of-bound tens-and-ones representation"
                )
            if not _is_canonical_number_sense_representation(tens, ones):
                raise ValueError(
                    "number_sense_20 contains a non-canonical tens-and-ones representation"
                )
        if classification["status"] == "malformed":
            raise ValueError(
                "number_sense_20 contains a non-canonical tens-and-ones representation"
            )


def _assert_practice_hints_do_not_reveal_answers(
    questions: Sequence[Mapping[str, object]],
) -> None:
    for question in questions[1:]:
        if question.get("type") != "single_choice":
            continue
        label = re.sub(r"\s+", "", _normalized_comparable(_correct_choice_label(question)))
        hint = re.sub(r"\s+", "", _normalized_comparable(question.get("hint")))
        if not label or not hint:
            continue
        leaked = False
        if re.fullmatch(r"\d+", label):
            escaped = re.escape(label)
            leaked = bool(
                re.search(
                    rf"(?:答案|结果|等于|得到|应选|选择)[^\d]{{0,4}}{escaped}(?!\d)|=\s*{escaped}(?!\d)",
                    hint,
                )
            )
        elif len(label) >= 2:
            leaked = label in hint
        elif label in {"上", "下", "左", "右", "圆"}:
            leaked = bool(
                re.search(
                    rf"(?:答案|在|看|向|往|选|选择|应选|是).{{0,4}}{re.escape(label)}(?:边|面|方|形)?",
                    hint,
                )
            )
        if leaked:
            raise ValueError("practice hint reveals the correct choice label")


def _validate_primary_one_math_blueprint(
    command: QuestionPhaseCommand, questions: Sequence[Mapping[str, object]]
) -> None:
    if command.grade_code != "primary_1" or command.subject != "math":
        return
    skill_id = str(command.boundary.get("skillId") or "")
    _assert_practice_hints_do_not_reveal_answers(questions)

    practice = questions[1:5]
    independent = questions[3:5]
    if skill_id == "number_sense_20":
        _assert_number_sense_representations(questions)
        if not _number_sense_adjacent_answer_is_recomputable(questions[1]):
            raise ValueError(
                "number_sense_20 q2 number-order question must have one "
                "host-recomputable adjacent answer"
            )
        uses_twenty = any(
            re.search(
                r"(?<!\d)20(?!\d|\s*以内)",
                f"{question.get('prompt') or ''} {_correct_choice_label(question)}",
            )
            for question in practice
        )
        if not uses_twenty:
            raise ValueError("number_sense_20 practice must use boundary value 20")
        kinds = {_number_sense_kind(question) for question in independent}
        if not {"comparison", "composition"}.issubset(kinds):
            raise ValueError("number_sense_20 q4-q5 must cover comparison and composition")
        if not _number_sense_adjacent_answer_is_recomputable(questions[1]) and not any(
            re.search(
                r"顺序|往前|往后|跳过|排列|相邻|排在|从\s*\d+\s*(?:数|跳|走).*\d+",
                unicodedata.normalize("NFKC", str(question.get("prompt") or "")),
            )
            for question in practice
        ):
            raise ValueError("number_sense_20 practice must include number-order evidence")
        cross_tens = False
        for question in practice:
            if _number_sense_kind(question) != "comparison":
                continue
            prompt = re.sub(
                r"20\s*以内",
                "",
                unicodedata.normalize("NFKC", str(question.get("prompt") or "")),
            )
            values = [
                int(match.group(1))
                for match in re.finditer(r"(?<!\d)(\d{1,2})(?!\d)", prompt)
                if 0 <= int(match.group(1)) <= 20
            ]
            distinct = list(dict.fromkeys(values))
            if len(distinct) >= 2 and distinct[0] // 10 != distinct[1] // 10:
                cross_tens = True
                break
        if not cross_tens:
            raise ValueError("number_sense_20 practice must include a cross-tens comparison")
        composition = questions[4]
        if composition.get("type") != "single_choice":
            raise ValueError("number_sense_20 q5 composition must be single_choice")
        target = _number_sense_composition_prompt_target(
            composition, require_from_composition=True
        )
        if target is None:
            raise ValueError(
                "number_sense_20 q5 must give a target numeral before its composition"
            )
        represented: dict[str, int] = {}
        raw_choices = composition.get("choices")
        choices = raw_choices if isinstance(raw_choices, list) else []
        for choice in choices:
            if not isinstance(choice, Mapping):
                raise ValueError("number_sense_20 q5 choice is invalid")
            label = unicodedata.normalize("NFKC", str(choice.get("label") or ""))
            representation = re.fullmatch(r"\s*(\d+)\s*个十\s*和\s*(\d+)\s*个一\s*", label)
            if representation is None:
                raise ValueError("number_sense_20 q5 choice label is invalid")
            represented_value = int(representation.group(1)) * 10 + int(representation.group(2))
            if not 0 <= represented_value <= 20:
                raise ValueError("number_sense_20 q5 choice is out of bounds")
            represented[str(choice.get("id") or "")] = represented_value
        if len(set(represented.values())) != len(represented):
            raise ValueError("number_sense_20 q5 choices represent duplicate values")
        if represented.get(str(composition.get("answer") or "")) != target:
            raise ValueError("number_sense_20 q5 correct choice differs from target")
        return

    if skill_id == "shapes_position":
        shape_terms = re.compile(r"圆形|三角形|正方形|长方形")
        position_terms = re.compile(r"上面|下面|左面|右面|上边|下边|左边|右边|上下左右")

        def kind(question: Mapping[str, object]) -> str:
            prompt = unicodedata.normalize("NFKC", str(question.get("prompt") or ""))
            labels = " ".join(
                str(choice.get("label") or "")
                for choice in question.get("choices", [])
                if isinstance(choice, Mapping)
            )
            if re.search(r"哪个.*图形|是什么图形|什么形状|辨认", prompt) and shape_terms.search(labels):
                return "shape"
            if position_terms.search(f"{prompt} {labels}"):
                return "position"
            return "other"

        kinds = {kind(question) for question in independent}
        if not {"shape", "position"}.issubset(kinds):
            raise ValueError("shapes_position q4-q5 must cover shape and position")
        unseen = re.compile(
            r"图中|图里|图片中|画面中|示意图|如下图|所示|这些图形|上图|下图|左图|右图|上层|下层|第一排|第二排"
        )
        if any(unseen.search(str(question.get("prompt") or "")) for question in questions):
            raise ValueError("shapes_position question references an unseen layout")
        for question in questions:
            if question.get("type") != "single_choice":
                continue
            labels = [
                unicodedata.normalize("NFKC", str(choice.get("label") or "")).replace(" ", "")
                for choice in question.get("choices", [])
                if isinstance(choice, Mapping)
            ]
            answer_label = re.sub(r"\s+", "", _correct_choice_label(question))
            if answer_label != "长方形" or "正方形" not in labels:
                continue
            prompt = re.sub(
                r"\s+",
                "",
                unicodedata.normalize("NFKC", str(question.get("prompt") or "")),
            )
            discriminators = (
                r"四条边(?:并非|不是|不都|不全)(?:一样长|相等)",
                r"相邻(?:的)?(?:两条)?边(?:长度)?(?:不同|不一样|不相等)",
                r"两条长.{0,8}两条短",
                r"有长边.{0,8}(?:也有|和|还有)短边",
                r"长和宽(?:不同|不一样|不相等)",
            )
            if not any(re.search(pattern, prompt) for pattern in discriminators):
                raise ValueError("shapes_position rectangle question does not exclude square")
        for question in independent:
            if kind(question) != "shape":
                continue
            label = re.sub(r"\s+", "", _normalized_comparable(_correct_choice_label(question)))
            prompt = re.sub(r"\s+", "", _normalized_comparable(question.get("prompt")))
            if label and label in prompt:
                raise ValueError("shapes_position prompt repeats its correct shape label")
        return

    if skill_id != "addition_subtraction_20":
        return
    for question in questions:
        values = [int(value) for value in re.findall(r"(?<!\d)(\d+)(?!\d)", _question_public_text(question))]
        if any(value > 20 for value in values):
            raise ValueError("addition_subtraction_20 public values exceed the boundary")
    operations: set[str] = set()
    for question in independent:
        if question.get("type") != "numeric":
            raise ValueError("addition_subtraction_20 independent questions must be numeric")
        match = re.fullmatch(r"(\d+)([+-])(\d+)", str(question.get("verificationExpression") or ""))
        if match is None:
            raise ValueError("addition_subtraction_20 independent expression is invalid")
        left, operation, right = int(match.group(1)), match.group(2), int(match.group(3))
        answer = left + right if operation == "+" else left - right
        if answer < 0 or any(value > 20 for value in (left, right, answer)):
            raise ValueError("addition_subtraction_20 arithmetic exceeds the boundary")
        if str(question.get("answer") or "") != str(answer):
            raise ValueError("addition_subtraction_20 expression differs from answer")
        operations.add(operation)
    if operations != {"+", "-"}:
        raise ValueError("addition_subtraction_20 must cover addition and subtraction")
    if not any(
        re.search(r"有\s*\d+|又|一共|还剩|拿走|吃掉|来了|走了|买了|送给|奖励", str(question.get("prompt") or ""))
        for question in independent
    ):
        raise ValueError("addition_subtraction_20 requires an independent story problem")


def _normalize_course_question(
    raw: object, index: int, command: QuestionPhaseCommand
) -> dict[str, object]:
    field = f"candidateCourse.content.questions[{index}]"
    value = _plain_mapping(raw, field)
    question_type = _normalized_string(value.get("type"), f"{field}.type", maximum=40)
    type_fields = {
        "numeric": {"answer", "verificationExpression", "evaluation"},
        "single_choice": {"answer", "choices", "evaluation"},
        "exact_text": {"answer", "evaluation"},
        "accepted_text": {"answer", "acceptedAnswers", "evaluation"},
        "sequence": {"answer", "choices", "evaluation"},
    }.get(question_type)
    if type_fields is None:
        raise ValueError(f"{field}.type is invalid")
    base_fields = {"id", "type", "prompt", "skill", "hint", "explanation"}
    _require_exact_keys(value, base_fields | type_fields, field)
    normalized: dict[str, object] = {
        "id": _normalized_string(value.get("id"), f"{field}.id", maximum=120),
        "type": question_type,
        "prompt": _normalized_string(value.get("prompt"), f"{field}.prompt", maximum=1200),
        "skill": _normalized_string(value.get("skill"), f"{field}.skill", maximum=160),
        "hint": _normalized_string(value.get("hint"), f"{field}.hint", maximum=1000),
        "explanation": _normalized_string(value.get("explanation"), f"{field}.explanation", maximum=1500),
    }
    expected_id = (
        f"{question_candidate_request_slug(command.generation_request_id, maximum=64, logical_attempt=command.logical_attempt)}"
        f"_q{index + 1}"
    )
    if normalized["id"] != expected_id or normalized["skill"] != command.boundary.get("skillTitle"):
        raise ValueError(f"{field} host-owned identity is invalid")
    if question_type in {"accepted_text", "sequence"}:
        answer = _normalized_string_array(
            value.get("answer"), f"{field}.answer", minimum=1, maximum=8, string_maximum=500
        )
    else:
        answer = _normalized_string(value.get("answer"), f"{field}.answer", maximum=500)
    normalized["answer"] = answer
    if question_type == "numeric":
        expression = _normalize_arithmetic_expression(value.get("verificationExpression"), field)
        _assert_numeric_answer(str(answer), expression, field)
        normalized["verificationExpression"] = expression
    if question_type == "accepted_text":
        accepted = _normalized_string_array(
            value.get("acceptedAnswers"), f"{field}.acceptedAnswers", minimum=1, maximum=8, string_maximum=500
        )
        if accepted != answer:
            raise ValueError(f"{field}.acceptedAnswers differs from answer")
        _assert_unique_accepted_text_answers(
            answer, command.subject, f"{field}.answer"
        )
        normalized["acceptedAnswers"] = accepted
    if question_type in {"single_choice", "sequence"}:
        choices_value = value.get("choices")
        if not isinstance(choices_value, list) or not 2 <= len(choices_value) <= 8:
            raise ValueError(f"{field}.choices is invalid")
        choices = [
            _normalize_choice(item, f"{field}.choices[{choice_index}]")
            for choice_index, item in enumerate(choices_value)
        ]
        if len({_normalized_comparable(item["id"]) for item in choices}) != len(choices) or len(
            {_normalized_comparable(item["label"]) for item in choices}
        ) != len(choices):
            raise ValueError(f"{field}.choices contains duplicates")
        if question_type == "single_choice" and answer not in {item["id"] for item in choices}:
            raise ValueError(f"{field}.answer must be a choice id")
        if question_type == "sequence" and (
            len(answer) != len(choices)
            or len(set(answer)) != len(answer)
            or any(item not in {choice["id"] for choice in choices} for item in answer)
        ):
            raise ValueError(f"{field}.answer must order every choice")
        normalized["choices"] = choices
    evaluation = _plain_mapping(value.get("evaluation"), f"{field}.evaluation")
    expected_key = {
        "numeric": "expected",
        "single_choice": "expectedOptionId",
        "exact_text": "expected",
        "accepted_text": "acceptedAnswers",
        "sequence": "expectedSequence",
    }[question_type]
    _require_exact_keys(evaluation, {expected_key, "normalization"}, f"{field}.evaluation")
    expected_value = _assert_bounded_json(evaluation[expected_key], f"{field}.evaluation.{expected_key}")
    normalizations = _normalized_string_array(
        evaluation.get("normalization"), f"{field}.evaluation.normalization", minimum=1, maximum=8, string_maximum=80
    )
    if expected_value != answer or normalizations != _normalization_for(question_type, command.subject):
        raise ValueError(f"{field}.evaluation is not canonical answer authority")
    normalized["evaluation"] = {expected_key: expected_value, "normalization": normalizations}
    if _canonical_json(value) != _canonical_json(normalized):
        raise ValueError(f"{field} is not canonical")
    return normalized


def _candidate_projection_from_course(course: Mapping[str, object]) -> dict[str, object]:
    content = course["content"]
    assert isinstance(content, Mapping)
    flow = content["teachingFlow"]
    assert isinstance(flow, Mapping)
    questions = content["questions"]
    assert isinstance(questions, list)
    projected_questions = []
    for item in questions:
        assert isinstance(item, Mapping)
        projected_questions.append(
            {
                key: copy.deepcopy(value)
                for key, value in item.items()
                if key not in {"id", "evaluation"}
            }
        )
    return {
        "title": course["title"],
        "intro": content["intro"],
        "estimatedMinutes": content["estimatedMinutes"],
        "teachingFlow": {
            "teach": copy.deepcopy(flow["teach"]),
            "recap": copy.deepcopy(flow["recap"]),
        },
        "questions": projected_questions,
    }


def _build_candidate_course(
    command: QuestionPhaseCommand, candidate: Mapping[str, object]
) -> dict[str, object]:
    skill_id = str(command.boundary.get("skillId") or "")
    raw_questions = candidate["questions"]
    assert isinstance(raw_questions, list)
    questions: list[dict[str, object]] = []
    for index, raw in enumerate(raw_questions):
        assert isinstance(raw, Mapping)
        question = copy.deepcopy(dict(raw))
        question_id = (
            f"{question_candidate_request_slug(command.generation_request_id, maximum=64, logical_attempt=command.logical_attempt)}"
            f"_q{index + 1}"
        )
        question_type = str(question["type"])
        expected_key = {
            "numeric": "expected",
            "single_choice": "expectedOptionId",
            "exact_text": "expected",
            "accepted_text": "acceptedAnswers",
            "sequence": "expectedSequence",
        }[question_type]
        evaluation = {
            expected_key: copy.deepcopy(question["answer"]),
            "normalization": _normalization_for(question_type, command.subject),
        }
        questions.append(
            {
                "id": question_id,
                **question,
                "evaluation": evaluation,
            }
        )
    flow = candidate["teachingFlow"]
    assert isinstance(flow, Mapping)
    question_ids = [str(item["id"]) for item in questions]
    return {
        "id": question_candidate_course_id(
            grade_code=command.grade_code,
            subject=command.subject,
            skill_id=skill_id,
            generation_request_id=command.generation_request_id,
            logical_attempt=command.logical_attempt,
        ),
        "version": "0.0.0-candidate",
        "gradeCode": command.grade_code,
        "subject": command.subject,
        "nodeCode": skill_id,
        "title": candidate["title"],
        "objective": ";".join(str(item) for item in command.boundary.get("learningObjectives", [])),
        "status": "unverified",
        "content": {
            **({"difficultyCode": command.difficulty_code} if command.grade_code != "primary_1" else {}),
            "schemaVersion": "mira.learning.course.v1",
            "sessionKind": "lesson",
            "outcomeMode": "scored_deterministic",
            "sourceAuthority": {
                "basis": "provided_skill_boundary",
                "contentOrigin": "openmaic_kimi_candidate",
                "textbookDependency": "none",
            },
            "reviewPolicy": "programmatic_guarded",
            "intro": candidate["intro"],
            "estimatedMinutes": candidate["estimatedMinutes"],
            "teachingFlow": {
                "schemaVersion": TEACHING_FLOW_SCHEMA_VERSION,
                "teach": copy.deepcopy(flow["teach"]),
                "demoQuestionId": question_ids[0],
                "guidedQuestionIds": question_ids[1:3],
                "independentQuestionIds": question_ids[3:5],
                "recap": copy.deepcopy(flow["recap"]),
            },
            "questions": questions,
        },
    }


def question_candidate_request_slug(
    request_id: str,
    *,
    maximum: int,
    logical_attempt: int,
) -> str:
    if (
        not isinstance(request_id, str)
        or not request_id
        or isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or maximum < 14
        or isinstance(logical_attempt, bool)
        or logical_attempt not in {1, 2}
    ):
        raise ValueError("candidate request identity is invalid")
    raw = re.sub(r"[^A-Za-z0-9]+", "_", request_id)
    if logical_attempt == 2 and len(raw) > maximum:
        suffix = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:12]
        return raw[: maximum - len(suffix) - 1] + "_" + suffix
    return raw[:maximum]


def question_candidate_course_id(
    *,
    grade_code: str,
    subject: str,
    skill_id: str,
    generation_request_id: str,
    logical_attempt: int,
) -> str:
    for value in (grade_code, subject, skill_id):
        if not isinstance(value, str) or not value:
            raise ValueError("candidate course identity is invalid")
    skill_hash = hashlib.sha256(skill_id.encode("utf-8")).hexdigest()[:12]
    request_slug = question_candidate_request_slug(
        generation_request_id,
        maximum=48,
        logical_attempt=logical_attempt,
    )
    return f"candidate_{grade_code}_{subject}_{skill_hash}_{request_slug}"


def _normalize_candidate_course(
    raw: object,
    command: QuestionPhaseCommand,
    *,
    existing_fingerprints: Sequence[str],
) -> dict[str, object]:
    field = "checkpoint.candidateCourse"
    value = _plain_mapping(raw, field)
    _require_exact_keys(
        value,
        {"id", "version", "gradeCode", "subject", "nodeCode", "title", "objective", "status", "content"},
        field,
    )
    content = _plain_mapping(value.get("content"), f"{field}.content")
    _require_exact_keys(
        content,
        {"schemaVersion", "sessionKind", "outcomeMode", "sourceAuthority", "reviewPolicy", "intro", "estimatedMinutes", "teachingFlow", "questions"} | ({"difficultyCode"} if command.grade_code != "primary_1" else set()),
        f"{field}.content",
    )
    authority = _plain_mapping(content.get("sourceAuthority"), f"{field}.content.sourceAuthority")
    _require_exact_keys(authority, {"basis", "contentOrigin", "textbookDependency"}, f"{field}.content.sourceAuthority")
    flow = _plain_mapping(content.get("teachingFlow"), f"{field}.content.teachingFlow")
    _require_exact_keys(
        flow,
        {"schemaVersion", "teach", "demoQuestionId", "guidedQuestionIds", "independentQuestionIds", "recap"},
        f"{field}.content.teachingFlow",
    )
    teach = _plain_mapping(flow.get("teach"), f"{field}.content.teachingFlow.teach")
    recap = _plain_mapping(flow.get("recap"), f"{field}.content.teachingFlow.recap")
    _require_exact_keys(teach, {"title", "sayText", "keyPoints"}, f"{field}.content.teachingFlow.teach")
    _require_exact_keys(recap, {"sayText"}, f"{field}.content.teachingFlow.recap")
    raw_questions = content.get("questions")
    if not isinstance(raw_questions, list) or len(raw_questions) != 5:
        raise ValueError(f"{field}.content.questions must contain five items")
    questions = [
        _normalize_course_question(question, index, command)
        for index, question in enumerate(raw_questions)
    ]
    estimated = content.get("estimatedMinutes")
    if type(estimated) is not int or not 5 <= estimated <= 30:
        raise ValueError(f"{field}.content.estimatedMinutes is invalid")
    normalized = {
        "id": _normalized_string(value.get("id"), f"{field}.id", maximum=240),
        "version": _normalized_string(value.get("version"), f"{field}.version", maximum=80),
        "gradeCode": _normalized_string(value.get("gradeCode"), f"{field}.gradeCode", maximum=40),
        "subject": _normalized_string(value.get("subject"), f"{field}.subject", maximum=40),
        "nodeCode": _normalized_string(value.get("nodeCode"), f"{field}.nodeCode", maximum=120),
        "title": _normalized_string(value.get("title"), f"{field}.title", maximum=160),
        "objective": _normalized_string(value.get("objective"), f"{field}.objective", maximum=6500),
        "status": _normalized_string(value.get("status"), f"{field}.status", maximum=40),
        "content": {
            **({"difficultyCode": command.difficulty_code} if command.grade_code != "primary_1" else {}),
            "schemaVersion": _normalized_string(content.get("schemaVersion"), f"{field}.content.schemaVersion", maximum=80),
            "sessionKind": _normalized_string(content.get("sessionKind"), f"{field}.content.sessionKind", maximum=40),
            "outcomeMode": _normalized_string(content.get("outcomeMode"), f"{field}.content.outcomeMode", maximum=80),
            "sourceAuthority": {
                "basis": _normalized_string(authority.get("basis"), f"{field}.content.sourceAuthority.basis", maximum=80),
                "contentOrigin": _normalized_string(authority.get("contentOrigin"), f"{field}.content.sourceAuthority.contentOrigin", maximum=120),
                "textbookDependency": _normalized_string(authority.get("textbookDependency"), f"{field}.content.sourceAuthority.textbookDependency", maximum=80),
            },
            "reviewPolicy": _normalized_string(content.get("reviewPolicy"), f"{field}.content.reviewPolicy", maximum=80),
            "intro": _normalized_string(content.get("intro"), f"{field}.content.intro", maximum=1200),
            "estimatedMinutes": estimated,
            "teachingFlow": {
                "schemaVersion": _normalized_string(flow.get("schemaVersion"), f"{field}.content.teachingFlow.schemaVersion", maximum=80),
                "teach": {
                    "title": _normalized_string(teach.get("title"), f"{field}.content.teachingFlow.teach.title", maximum=160),
                    "sayText": _normalized_string(teach.get("sayText"), f"{field}.content.teachingFlow.teach.sayText", maximum=1200),
                    "keyPoints": _normalized_string_array(teach.get("keyPoints"), f"{field}.content.teachingFlow.teach.keyPoints", minimum=1, maximum=3, string_maximum=200),
                },
                "demoQuestionId": _normalized_string(flow.get("demoQuestionId"), f"{field}.content.teachingFlow.demoQuestionId", maximum=120),
                "guidedQuestionIds": _normalized_string_array(flow.get("guidedQuestionIds"), f"{field}.content.teachingFlow.guidedQuestionIds", minimum=2, maximum=2, string_maximum=120),
                "independentQuestionIds": _normalized_string_array(flow.get("independentQuestionIds"), f"{field}.content.teachingFlow.independentQuestionIds", minimum=2, maximum=2, string_maximum=120),
                "recap": {
                    "sayText": _normalized_string(recap.get("sayText"), f"{field}.content.teachingFlow.recap.sayText", maximum=600)
                },
            },
            "questions": questions,
        },
    }
    if _canonical_json(value) != _canonical_json(normalized):
        raise ValueError(f"{field} is not canonical")
    projection = _candidate_projection_from_course(normalized)
    compiled = _normalize_candidate_projection(
        projection,
        command,
        compiled=True,
        require_canonical=True,
        existing_fingerprints=existing_fingerprints,
    )
    expected = _build_candidate_course(command, compiled)
    if _canonical_json(normalized) != _canonical_json(expected):
        raise ValueError(f"{field} does not equal pure builder output")
    return normalized


def _public_questions(course: Mapping[str, object]) -> list[dict[str, object]]:
    content = course["content"]
    assert isinstance(content, Mapping)
    questions = content["questions"]
    assert isinstance(questions, list)
    result: list[dict[str, object]] = []
    for question in questions:
        assert isinstance(question, Mapping)
        public = {
            "id": question["id"],
            "type": question["type"],
            "prompt": question["prompt"],
        }
        if "choices" in question:
            raw_choices = question["choices"]
            assert isinstance(raw_choices, list)
            public["choices"] = [
                {"id": choice["id"], "label": choice["label"]}
                for choice in raw_choices
                if isinstance(choice, Mapping)
            ]
        result.append(public)
    return result


def _normalize_teaching_review(raw: object) -> dict[str, object]:
    value = _plain_mapping(raw, "teachingReview")
    _require_exact_keys(value, {"passed", "issues"}, "teachingReview")
    passed = value.get("passed")
    if type(passed) is not bool:
        raise ValueError("teachingReview.passed must be a boolean")
    issues = _normalized_string_array(
        value.get("issues"), "teachingReview.issues", maximum=3, string_maximum=300
    )
    if passed and issues:
        raise ValueError("passed teaching review cannot contain issues")
    if not passed and not issues:
        raise ValueError("failed teaching review requires issues")
    return {"passed": passed, "issues": issues}


def _normalize_independent_answer(
    raw: object,
    question: Mapping[str, object],
    index: int,
) -> object:
    field = f"independent answers[{index}].answer"
    if question["type"] == "sequence":
        answer = _normalized_string_array(raw, field, minimum=1, maximum=8, string_maximum=80)
        choices = question.get("choices")
        assert isinstance(choices, list)
        ids = [str(choice["id"]) for choice in choices if isinstance(choice, Mapping)]
        if len(answer) != len(ids) or len(set(answer)) != len(answer) or any(item not in ids for item in answer):
            raise ValueError(f"{field} must order all public choice ids")
        return answer
    answer = _normalized_string(raw, field, maximum=500)
    if question["type"] == "single_choice":
        choices = question.get("choices")
        assert isinstance(choices, list)
        if answer not in {str(choice["id"]) for choice in choices if isinstance(choice, Mapping)}:
            raise ValueError(f"{field} must be a public choice id")
    return answer


def _normalize_independent_solution(
    raw: object,
    command: QuestionPhaseCommand,
    candidate_course: Mapping[str, object],
    *,
    provider: Mapping[str, object],
) -> dict[str, object]:
    field = "checkpoint.independentSolution"
    value = _plain_mapping(raw, field)
    _require_exact_keys(
        value,
        {"schemaVersion", "solver", "independentFromGeneration", "verificationRequestId", "publicQuestionHash", "gradeCode", "subject", "skillId", "answers", "teachingReview"},
        field,
    )
    public_questions = _public_questions(candidate_course)
    raw_answers = value.get("answers")
    if not isinstance(raw_answers, list) or len(raw_answers) != len(public_questions):
        raise ValueError(f"{field}.answers must cover public questions")
    question_by_id = {str(item["id"]): item for item in public_questions}
    seen: set[str] = set()
    answers: list[dict[str, object]] = []
    for index, raw_answer in enumerate(raw_answers):
        item = _plain_mapping(raw_answer, f"{field}.answers[{index}]")
        question_id = _normalized_string(item.get("questionId"), f"{field}.answers[{index}].questionId", maximum=120)
        question = question_by_id.get(question_id)
        if question is None or question_id in seen:
            raise ValueError(f"{field}.answers question ids are invalid")
        seen.add(question_id)
        numeric = question["type"] == "numeric"
        _require_exact_keys(
            item,
            {"questionId", "answer", "derivedExpression"} if numeric else {"questionId", "answer"},
            f"{field}.answers[{index}]",
        )
        answer = _normalize_independent_answer(item.get("answer"), question, index)
        normalized_answer: dict[str, object] = {"questionId": question_id, "answer": answer}
        if numeric:
            expression = _normalize_arithmetic_expression(
                item.get("derivedExpression"), f"{field}.answers[{index}]"
            )
            if not re.search(r"[+\-*/]", expression) or _normalized_comparable(expression) == _normalized_comparable(answer):
                raise ValueError("numeric independent derivation must be nonconstant")
            prompt_numbers = {
                _normalize_numeric_token(token)
                for token in re.findall(r"\d+(?:\.\d+)?", str(question["prompt"]))
            }
            expression_numbers = [
                _normalize_numeric_token(token)
                for token in re.findall(r"\d+(?:\.\d+)?", expression)
            ]
            if len(expression_numbers) < 2 or any(token not in prompt_numbers for token in expression_numbers):
                raise ValueError("numeric derivation uses an unauthorized operand")
            _assert_numeric_answer(str(answer), expression, f"{field}.answers[{index}]")
            normalized_answer["derivedExpression"] = expression
        answers.append(normalized_answer)
    if len(seen) != len(public_questions):
        raise ValueError(f"{field}.answers omitted a public question")
    public_json = json.dumps(public_questions, ensure_ascii=False, separators=(",", ":"))
    provider_solver = f"{provider['name']}:{provider['model']}:fresh_call"
    solver = value.get("solver")
    host_solver_by_skill = {
        "addition_subtraction_20": PRIMARY_ONE_ADD_SUB_HOST_SOLVER,
        "number_sense_20": PRIMARY_ONE_NUMBER_SENSE_HOST_SOLVER,
        "simple_sentences": PRIMARY_ONE_SIMPLE_SENTENCE_HOST_SOLVER,
        "characters_words": PRIMARY_ONE_CHARACTER_WORD_HOST_SOLVER,
    }
    expected_host_solver = (
        host_solver_by_skill.get(str(command.boundary.get("skillId") or ""))
        if command.grade_code == "primary_1"
        and (
            command.subject == "math"
            or (
                command.subject == "chinese"
                and command.boundary.get("skillId")
                in {"simple_sentences", "characters_words"}
            )
        )
        else None
    )
    expected_solver = (
        expected_host_solver
        if solver == expected_host_solver and expected_host_solver is not None
        else provider_solver
    )
    expected = {
        "schemaVersion": "mira.learning.independent-solution.v1",
        "solver": expected_solver,
        "independentFromGeneration": True,
        "verificationRequestId": command.generation_request_id,
        "publicQuestionHash": hashlib.sha256(public_json.encode("utf-8")).hexdigest(),
        "gradeCode": command.grade_code,
        "subject": command.subject,
        "skillId": command.boundary.get("skillId"),
        "answers": answers,
        "teachingReview": _normalize_teaching_review(value.get("teachingReview")),
    }
    if _canonical_json(value) != _canonical_json(expected):
        raise ValueError(f"{field} failed pure builder validation")
    return expected


def _normalize_numeric_token(value: str) -> str:
    try:
        number = float(value)
    except ValueError:
        return value
    if number.is_integer():
        return str(int(number))
    return format(number, ".15g")


def _normalize_question_fingerprints(raw: object) -> list[dict[str, str]]:
    if not isinstance(raw, list) or len(raw) != 5:
        raise ValueError("checkpoint.questionFingerprints must contain five items")
    result: list[dict[str, str]] = []
    for index, raw_item in enumerate(raw):
        field = f"checkpoint.questionFingerprints[{index}]"
        item = _plain_mapping(raw_item, field)
        _require_exact_keys(item, {"questionId", "fingerprint"}, field)
        fingerprint = _normalized_string(item.get("fingerprint"), f"{field}.fingerprint", maximum=64)
        if not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
            raise ValueError(f"{field}.fingerprint is invalid")
        result.append(
            {
                "questionId": _normalized_string(item.get("questionId"), f"{field}.questionId", maximum=120),
                "fingerprint": fingerprint,
            }
        )
    if len({item["questionId"] for item in result}) != 5 or len({item["fingerprint"] for item in result}) != 5:
        raise ValueError("checkpoint.questionFingerprints contains duplicates")
    return result


def _normalize_validation(raw: object) -> dict[str, object]:
    field = "checkpoint.validation"
    value = _plain_mapping(raw, field)
    keys = {
        "schemaValidated", "boundaryPreserved", "plainTextOnly", "questionCount",
        "allowedQuestionTypes", "guidedQuestionTypes", "existingFingerprintsChecked",
        "duplicateFingerprints", "independentSolutionRequired", "independentSolutionProvided",
        "teachingFlowSchemaValidated", "teachingReviewRequired",
        "programmaticNumericRecalculationRequired",
    }
    _require_exact_keys(value, keys, field)
    booleans = (
        "schemaValidated", "boundaryPreserved", "plainTextOnly",
        "independentSolutionRequired", "independentSolutionProvided",
        "teachingFlowSchemaValidated", "teachingReviewRequired",
        "programmaticNumericRecalculationRequired",
    )
    if any(type(value.get(key)) is not bool for key in booleans):
        raise ValueError(f"{field} boolean evidence is invalid")
    question_count = value.get("questionCount")
    existing_count = value.get("existingFingerprintsChecked")
    if type(question_count) is not int or type(existing_count) is not int or any(
        abs(item) > 9_007_199_254_740_991 for item in (question_count, existing_count)
    ):
        raise ValueError(f"{field} integer evidence is invalid")
    return {
        "schemaValidated": value["schemaValidated"],
        "boundaryPreserved": value["boundaryPreserved"],
        "plainTextOnly": value["plainTextOnly"],
        "questionCount": question_count,
        "allowedQuestionTypes": _normalized_string_array(value.get("allowedQuestionTypes"), f"{field}.allowedQuestionTypes", minimum=1, maximum=10, string_maximum=80),
        "guidedQuestionTypes": _normalized_string_array(value.get("guidedQuestionTypes"), f"{field}.guidedQuestionTypes", minimum=1, maximum=10, string_maximum=80),
        "existingFingerprintsChecked": existing_count,
        "duplicateFingerprints": _normalized_string_array(value.get("duplicateFingerprints"), f"{field}.duplicateFingerprints", maximum=5, string_maximum=64),
        "independentSolutionRequired": value["independentSolutionRequired"],
        "independentSolutionProvided": value["independentSolutionProvided"],
        "teachingFlowSchemaValidated": value["teachingFlowSchemaValidated"],
        "teachingReviewRequired": value["teachingReviewRequired"],
        "programmaticNumericRecalculationRequired": value["programmaticNumericRecalculationRequired"],
    }


def _build_question_fingerprints(
    command: QuestionPhaseCommand, course: Mapping[str, object]
) -> list[dict[str, str]]:
    content = course["content"]
    assert isinstance(content, Mapping)
    questions = content["questions"]
    assert isinstance(questions, list)
    return [
        {"questionId": str(question["id"]), "fingerprint": _question_fingerprint(command, question)}
        for question in questions
        if isinstance(question, Mapping)
    ]


def _build_validation(
    course: Mapping[str, object], *, existing_count: int
) -> dict[str, object]:
    content = course["content"]
    assert isinstance(content, Mapping)
    questions = content["questions"]
    assert isinstance(questions, list)
    return {
        "schemaValidated": True,
        "boundaryPreserved": True,
        "plainTextOnly": True,
        "questionCount": len(questions),
        "allowedQuestionTypes": sorted(_SAFE_QUESTION_TYPES),
        "guidedQuestionTypes": sorted(_GUIDED_QUESTION_TYPES),
        "existingFingerprintsChecked": existing_count,
        "duplicateFingerprints": [],
        "independentSolutionRequired": True,
        "independentSolutionProvided": False,
        "teachingFlowSchemaValidated": True,
        "teachingReviewRequired": True,
        "programmaticNumericRecalculationRequired": any(
            isinstance(question, Mapping) and question.get("type") == "numeric"
            for question in questions
        ),
    }


def _normalize_consistency_repair(
    raw: object,
    candidate_course: Mapping[str, object],
    command: QuestionPhaseCommand,
) -> dict[str, object]:
    field = "checkpoint.repair"
    value = _plain_mapping(raw, field)
    _require_exact_keys(value, {"title", "intro", "teach", "recap", "questionGuidance"}, field)
    teach = _plain_mapping(value.get("teach"), f"{field}.teach")
    recap = _plain_mapping(value.get("recap"), f"{field}.recap")
    _require_exact_keys(teach, {"title", "sayText", "keyPoints"}, f"{field}.teach")
    _require_exact_keys(recap, {"sayText"}, f"{field}.recap")
    content = candidate_course["content"]
    assert isinstance(content, Mapping)
    questions = content["questions"]
    assert isinstance(questions, list)
    raw_guidance = value.get("questionGuidance")
    if not isinstance(raw_guidance, list) or len(raw_guidance) != len(questions):
        raise ValueError(f"{field}.questionGuidance must cover every question")
    guidance: list[dict[str, str]] = []
    for index, (raw_item, question) in enumerate(zip(raw_guidance, questions)):
        assert isinstance(question, Mapping)
        item_field = f"{field}.questionGuidance[{index}]"
        item = _plain_mapping(raw_item, item_field)
        _require_exact_keys(item, {"questionId", "hint", "explanation"}, item_field)
        question_id = _normalized_string(item.get("questionId"), f"{item_field}.questionId", maximum=120)
        if question_id != question["id"]:
            raise ValueError(f"{item_field}.questionId must match question order")
        guidance.append(
            {
                "questionId": question_id,
                "hint": _normalized_string(item.get("hint"), f"{item_field}.hint", maximum=800),
                "explanation": _normalized_string(item.get("explanation"), f"{item_field}.explanation", maximum=1500),
            }
        )
    normalized = {
        "title": _normalized_string(value.get("title"), f"{field}.title", maximum=160),
        "intro": _normalized_string(value.get("intro"), f"{field}.intro", maximum=1200),
        "teach": {
            "title": _normalized_string(teach.get("title"), f"{field}.teach.title", maximum=160),
            "sayText": _normalized_string(teach.get("sayText"), f"{field}.teach.sayText", maximum=1200),
            "keyPoints": _normalized_string_array(teach.get("keyPoints"), f"{field}.teach.keyPoints", minimum=1, maximum=3, string_maximum=200),
        },
        "recap": {
            "sayText": _normalized_string(recap.get("sayText"), f"{field}.recap.sayText", maximum=600)
        },
        "questionGuidance": guidance,
    }
    if _canonical_json(value) != _canonical_json(normalized):
        raise ValueError(f"{field} is not canonical")
    if command.boundary.get("skillId") == "number_sense_20":
        _assert_number_sense_representations(
            normalized,
            teaching_root_keys=frozenset({"teach", "recap"}),
        )
    return normalized


def _apply_consistency_repair(
    candidate_course: Mapping[str, object], repair: Mapping[str, object]
) -> dict[str, object]:
    repaired = copy.deepcopy(dict(candidate_course))
    content = repaired["content"]
    assert isinstance(content, dict)
    flow = content["teachingFlow"]
    assert isinstance(flow, dict)
    repaired["title"] = repair["title"]
    content["intro"] = repair["intro"]
    flow["teach"] = copy.deepcopy(repair["teach"])
    flow["recap"] = copy.deepcopy(repair["recap"])
    guidance = repair["questionGuidance"]
    assert isinstance(guidance, list)
    by_id = {
        str(item["questionId"]): item
        for item in guidance
        if isinstance(item, Mapping)
    }
    questions = content["questions"]
    assert isinstance(questions, list)
    for question in questions:
        assert isinstance(question, dict)
        item = by_id.get(str(question["id"]))
        if item is not None:
            question["hint"] = item["hint"]
            question["explanation"] = item["explanation"]
    return repaired


def _answer_values(question: Mapping[str, object]) -> list[str]:
    question_type = question.get("type")
    if question_type == "accepted_text":
        answer = question.get("answer")
        return [str(item) for item in answer] if isinstance(answer, list) else []
    if question_type == "single_choice":
        choices = question.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if isinstance(choice, Mapping) and choice.get("id") == question.get("answer"):
                    return [str(choice.get("label") or "")]
        return []
    if question_type == "sequence":
        choices = question.get("choices")
        answer = question.get("answer")
        if not isinstance(choices, list) or not isinstance(answer, list):
            return []
        labels = []
        for item in answer:
            match = next(
                (
                    choice
                    for choice in choices
                    if isinstance(choice, Mapping) and choice.get("id") == item
                ),
                None,
            )
            labels.append(str(match.get("label") if isinstance(match, Mapping) else item))
        return [" ".join(labels), "、".join(labels)]
    return [str(question.get("answer") or "")]


def _hint_explicitly_reveals(hint_value: object, answer_value: object) -> bool:
    hint = re.sub(r"\s+", "", _normalized_comparable(hint_value))
    answer = re.sub(r"\s+", "", _normalized_comparable(answer_value))
    if not answer:
        return False
    if hint == answer:
        return True
    escaped = re.escape(answer)
    lead = r"(?:正确答案(?:是|为)?|答案(?:是|为)?|结果(?:是|为)?|应选|选择|等于)"
    tail = r"(?:$|[,.!?;:，。！？；：])"
    return bool(
        re.search(
            rf"{lead}[：:]?[“\"']?{escaped}[”\"']?{tail}",
            hint,
            flags=re.IGNORECASE,
        )
    )


def _assert_question_does_not_reveal(
    question: Mapping[str, object],
    *,
    allow_choice_prompt_violation: bool,
) -> None:
    answers = _answer_values(question)
    if any(_hint_explicitly_reveals(question.get("hint"), answer) for answer in answers):
        raise ValueError("question hint directly reveals its answer")
    if any(_prompt_explicitly_reveals(question.get("prompt"), answer) for answer in answers):
        raise ValueError("question prompt directly reveals its answer")
    if (
        question.get("type") == "single_choice"
        and not allow_choice_prompt_violation
        and _choice_prompt_violation_indexes([question])
    ):
        raise ValueError("question prompt repeats rendered choice labels")


def _prompt_explicitly_reveals(prompt_value: object, answer_value: object) -> bool:
    prompt = re.sub(r"\s+", "", _normalized_comparable(prompt_value))
    answer = re.sub(r"\s+", "", _normalized_comparable(answer_value))
    if not answer:
        return False
    escaped = re.escape(answer)
    lead = r"(?:正确答案(?:是|为)?|答案(?:是|为)?|结果(?:是|为)?|应选|请选择|直接回答|等于)"
    tail = r"(?:$|[,.!?;:，。！？；：])"
    if re.search(rf"{lead}[：:]?[“\"']?{escaped}[”\"']?{tail}", prompt, flags=re.IGNORECASE):
        return True
    return bool(re.search(rf"=[“\"']?{escaped}[”\"']?(?:$|[,.!;:，。！；：])", prompt, flags=re.IGNORECASE))


def _primary_add_sub_signature(question: Mapping[str, object]) -> tuple[str, int, int, int] | None:
    if question.get("type") == "numeric":
        match = re.fullmatch(r"\s*(\d{1,2})\s*([+-])\s*(\d{1,2})\s*", str(question.get("verificationExpression") or ""))
        if match is None:
            return None
        left, operator, right = int(match.group(1)), match.group(2), int(match.group(3))
        return ("addition" if operator == "+" else "subtraction", left, right, left + right if operator == "+" else left - right)
    if question.get("type") != "single_choice":
        return None
    answer_values = _answer_values(question)
    answer_match = re.search(r"(?:^|\D)(\d{1,2})(?!\d)", answer_values[0] if answer_values else "")
    operands = [int(item) for item in re.findall(r"(?:^|\D)(\d{1,2})(?!\d)", _normalized_comparable(question.get("prompt")))]
    if answer_match is None or len(operands) < 2:
        return None
    left, right = operands[:2]
    answer = int(answer_match.group(1))
    compact = re.sub(r"\s+", "", _normalized_comparable(question.get("prompt")))
    if re.search(rf"{left}(?:\+|加(?:上)?){right}", compact):
        operation = "addition"
    elif re.search(rf"{left}(?:-|减(?:去)?){right}", compact):
        operation = "subtraction"
    elif re.search(r"借走|拿走|吃(?:了|掉)|还剩|剩下|送出|用掉|走了|减少", compact):
        operation = "subtraction"
    elif re.search(r"又|一共|合起来|总共|增加|放进|来了|得到|再加", compact):
        operation = "addition"
    else:
        return None
    expected = left + right if operation == "addition" else left - right
    return (operation, left, right, answer) if answer == expected else None


def _teaching_reveals_signature(text: str, signature: tuple[str, int, int, int]) -> bool:
    operation, left, right, answer = signature
    pairs = [(left, right)]
    if operation == "addition" and left != right:
        pairs.append((right, left))
    operator = r"(?:\+|加(?:上)?)" if operation == "addition" else r"(?:-|减(?:去)?)"
    answer_link = r"(?:=|等于|是|得|得到|结果(?:是|为)?|一共(?:是|有)?)"
    return any(
        re.search(rf"(^|\D){a}{operator}{b}.{{0,24}}{answer_link}.{{0,4}}{answer}(?!\d)", text)
        for a, b in pairs
    )


def _teaching_text_reveals_question(
    text_value: str, question: Mapping[str, object], question_number: int
) -> bool:
    compact_text = re.sub(r"\s+", "", _normalized_comparable(text_value))
    if not compact_text:
        return False
    signature = _primary_add_sub_signature(question)
    if signature and _teaching_reveals_signature(compact_text, signature):
        return True
    if not any(_prompt_explicitly_reveals(text_value, answer) for answer in _answer_values(question)):
        return False
    ordinal = {2: "二", 3: "三", 4: "四", 5: "五"}.get(question_number, "")
    if re.search(rf"(?:第(?:{question_number}|{ordinal})道?(?:题|练习)|q{question_number})", compact_text, flags=re.IGNORECASE):
        return True
    prompt_signature = re.sub(r"\s+", "", _normalized_comparable(question.get("prompt")))
    prompt_signature = re.sub(r"[?？。.!！]", "", prompt_signature)
    if len(prompt_signature) >= 8 and prompt_signature in compact_text:
        return True
    if question.get("type") == "numeric":
        expression = re.sub(r"\s+", "", _normalized_comparable(question.get("verificationExpression")))
        if len(expression) >= 3 and expression in compact_text:
            return True
    return False


def _practice_leak_indexes(
    teaching_flow: Mapping[str, object], questions: Sequence[Mapping[str, object]]
) -> list[int]:
    teach = teaching_flow.get("teach")
    recap = teaching_flow.get("recap")
    texts: list[str] = []
    if isinstance(teach, Mapping):
        for key in ("title", "sayText"):
            if isinstance(teach.get(key), str):
                texts.append(str(teach[key]))
        key_points = teach.get("keyPoints")
        if isinstance(key_points, list):
            texts.extend(str(item) for item in key_points if isinstance(item, str))
    if isinstance(recap, Mapping) and isinstance(recap.get("sayText"), str):
        texts.append(str(recap["sayText"]))
    return [
        index
        for index, question in enumerate(questions)
        if index > 0 and any(
            _teaching_text_reveals_question(text, question, index + 1)
            for text in texts
        )
    ]


def _choice_prompt_violation_indexes(
    questions: Sequence[Mapping[str, object]],
) -> list[int]:
    violations: list[int] = []
    for index, question in enumerate(questions):
        if question.get("type") != "single_choice":
            continue
        choices = question.get("choices")
        if not isinstance(choices, list):
            continue
        prompt = unicodedata.normalize("NFKC", str(question.get("prompt") or ""))
        occurrences: list[tuple[int, int]] = []
        for choice in choices:
            if not isinstance(choice, Mapping):
                continue
            label = unicodedata.normalize("NFKC", str(choice.get("label") or "")).strip()
            if len(re.sub(r"\s+", "", _normalized_comparable(label))) < 2:
                continue
            start = prompt.find(label)
            if start >= 0:
                occurrences.append((start, start + len(label)))
        occurrences.sort()
        for left, right in zip(occurrences, occurrences[1:]):
            between = prompt[left[1]:right[0]]
            if re.fullmatch(r"[\s、,，;；/／|]+", between):
                violations.append(index)
                break
    return violations


def _normalize_phase_output_checkpoint(
    prepared: PreparedQuestionPhase, raw: object
) -> dict[str, object]:
    io = _phase_io_for(prepared.command.phase, prepared.command.phase_ordinal)
    value = _plain_mapping(raw, "phase checkpoint")
    if value.get("phaseStatus") == "rejected":
        rejected = io.get("rejectedCheckpointKeys")
        if not isinstance(rejected, tuple):
            raise ValueError("phase cannot return rejected")
        _require_exact_keys(value, rejected, "phase checkpoint")
        code = value.get("rejectionCode")
        allowed = {
            "candidate_repair": {"candidate_repair_schema_rejected", "candidate_repair_originality_rejected"},
            "reconciliation": {"reconciliation_schema_rejected", "reconciliation_originality_rejected"},
            "consistency_repair": {"consistency_repair_schema_rejected"},
        }.get(prepared.command.phase, set())
        if code not in allowed:
            raise ValueError("phase rejection code mismatch")
        return {"phaseStatus": "rejected", "rejectionCode": code}
    if value.get("phaseStatus") != "accepted":
        raise ValueError("phaseStatus is invalid")
    accepted = io["acceptedCheckpointKeys"]
    assert isinstance(accepted, tuple)
    _require_exact_keys(value, accepted, "phase checkpoint")
    result: dict[str, object] = {"phaseStatus": "accepted"}
    request_checkpoint = prepared.request["checkpoint"]
    assert isinstance(request_checkpoint, Mapping)
    for key in accepted[1:]:
        if key == "outlinePlan":
            normalized_outline = _normalize_outline_plan(value[key])
            if (
                _is_exact_letters_sounds_phase(
                    prepared.command, "outline", 1
                )
                and normalized_outline != _canonical_letters_sounds_outline_plan()
            ):
                raise ValueError(
                    "checkpoint.outlinePlan is not the canonical Host outline"
                )
            result[key] = normalized_outline
        elif key == "rawCandidate":
            normalized_raw_candidate = _normalize_candidate_projection(
                value[key],
                prepared.command,
                compiled=False,
                require_canonical=False,
            )
            if (
                _is_exact_letters_sounds_phase(
                    prepared.command, "raw_candidate", 2
                )
                and normalized_raw_candidate
                != _canonical_letters_sounds_raw_candidate_seed()
            ):
                raise ValueError(
                    "checkpoint.rawCandidate is not the canonical Host seed"
                )
            if (
                _is_exact_number_sense_phase(
                    prepared.command, "raw_candidate", 2
                )
                and normalized_raw_candidate
                != _canonical_number_sense_raw_candidate_seed()
            ):
                raise ValueError(
                    "checkpoint.rawCandidate is not the canonical Host seed"
                )
            result[key] = normalized_raw_candidate
        elif key == "candidate":
            inventory = request_checkpoint.get("existingFingerprints", [])
            assert isinstance(inventory, list)
            result[key] = _normalize_candidate_projection(
                value[key],
                prepared.command,
                compiled=True,
                require_canonical=True,
                existing_fingerprints=inventory,
            )
        elif key == "hostCompilation":
            evidence = _plain_mapping(
                value[key], "checkpoint.hostCompilation"
            )
            _require_exact_keys(
                evidence,
                {"compiler", "source", "version"},
                "checkpoint.hostCompilation",
            )
            exact_number_sense = _is_exact_number_sense_phase3(
                prepared.command
            )
            exact_letters_sounds = _is_exact_letters_sounds_phase3(
                prepared.command
            )
            if exact_number_sense:
                expected_evidence = {
                    "compiler": "host_compiler",
                    "source": "canonical_skill_builder",
                    "version": NUMBER_SENSE_CANONICAL_BUILDER_VERSION,
                }
                if evidence != expected_evidence:
                    raise ValueError("checkpoint.hostCompilation is invalid")
                result[key] = expected_evidence
            elif exact_letters_sounds:
                expected_evidence = {
                    "compiler": "host_compiler",
                    "source": "canonical_skill_builder",
                    "version": LETTERS_SOUNDS_CANONICAL_BUILDER_VERSION,
                }
                if evidence != expected_evidence:
                    raise ValueError("checkpoint.hostCompilation is invalid")
                result[key] = expected_evidence
            else:
                source = evidence.get("source")
                if (
                    evidence.get("compiler") != "host_compiler"
                    or source
                    not in {
                        "candidate_repair_output",
                        "accepted_raw_candidate",
                    }
                    or evidence.get("version") != "v1"
                ):
                    raise ValueError("checkpoint.hostCompilation is invalid")
                result[key] = {
                    "compiler": "host_compiler",
                    "source": source,
                    "version": "v1",
                }
        elif key == "hostReconciliation":
            evidence = _plain_mapping(
                value[key], "checkpoint.hostReconciliation"
            )
            _require_exact_keys(
                evidence,
                {"reconciler", "source", "version"},
                "checkpoint.hostReconciliation",
            )
            source = evidence.get("source")
            if (
                evidence.get("reconciler") != "host_reconciler"
                or source
                not in {"reconciliation_output", "accepted_candidate"}
                or evidence.get("version") != "v1"
            ):
                raise ValueError("checkpoint.hostReconciliation is invalid")
            result[key] = {
                "reconciler": "host_reconciler",
                "source": source,
                "version": "v1",
            }
        elif key == "lessonText":
            result[key] = _normalize_lesson_text(value[key])
        elif key == "reconciliation":
            inventory = request_checkpoint.get("existingFingerprints", [])
            assert isinstance(inventory, list)
            result[key] = _normalize_reconciliation(
                value[key],
                prepared.command,
                existing_fingerprints=inventory,
            )
        elif key in {"candidateCourse", "repairedCandidateCourse"}:
            inventory = request_checkpoint.get("existingFingerprints", [])
            assert isinstance(inventory, list)
            result[key] = _normalize_candidate_course(
                value[key],
                prepared.command,
                existing_fingerprints=inventory,
            )
        elif key == "questionFingerprints":
            result[key] = _normalize_question_fingerprints(value[key])
        elif key == "validation":
            result[key] = _normalize_validation(value[key])
        elif key == "independentSolution":
            course = result.get("candidateCourse", result.get("repairedCandidateCourse"))
            if not isinstance(course, Mapping):
                raise ValueError("independent solution output requires normalized course")
            result[key] = _normalize_independent_solution(
                value[key],
                prepared.command,
                course,
                provider=prepared.provider,
            )
        elif key == "repair":
            course = request_checkpoint.get("candidateCourse")
            if not isinstance(course, Mapping):
                raise ValueError("repair output requires candidate course")
            result[key] = _normalize_consistency_repair(
                value[key], course, prepared.command
            )
        else:
            raise ValueError("phase checkpoint artifact is unsupported")
    if prepared.command.phase in {"independent_verification", "verification_after_repair"}:
        course = result.get("candidateCourse", result.get("repairedCandidateCourse"))
        if not isinstance(course, Mapping):
            raise ValueError("verification output requires course authority")
        inventory = request_checkpoint.get("existingFingerprints", [])
        assert isinstance(inventory, list)
        expected_fingerprints = _build_question_fingerprints(prepared.command, course)
        expected_validation = _build_validation(course, existing_count=len(inventory))
        if result.get("questionFingerprints") != expected_fingerprints or any(
            item["fingerprint"] in set(inventory) for item in expected_fingerprints
        ):
            raise ValueError("phase checkpoint question fingerprint authority mismatch")
        if result.get("validation") != expected_validation:
            raise ValueError("phase checkpoint validation authority mismatch")
        if prepared.command.phase == "independent_verification":
            candidate = request_checkpoint.get("candidate")
            if (
                not isinstance(candidate, Mapping)
                or str(course.get("title") or "")
                != str(candidate.get("title") or "")
            ):
                raise ValueError(
                    "phase 11 course title changed generated candidate title"
                )
        if prepared.command.phase == "verification_after_repair":
            original_course = request_checkpoint.get("candidateCourse")
            repair = request_checkpoint.get("repair")
            if not isinstance(original_course, Mapping) or not isinstance(repair, Mapping):
                raise ValueError("phase 14 input authority is missing")
            expected_course = _apply_consistency_repair(original_course, repair)
            if _canonical_json(course) != _canonical_json(expected_course):
                raise ValueError("phase 14 repaired course is not deterministic")
            if result.get("questionFingerprints") != request_checkpoint.get("questionFingerprints") or result.get("validation") != request_checkpoint.get("validation"):
                raise ValueError("phase 14 changed immutable phase-11 evidence")
    if (
        prepared.command.boundary.get("skillId") == "number_sense_20"
        and prepared.command.phase != "raw_candidate"
    ):
        _assert_number_sense_representations(result)
    return result


def _assert_bounded_json(value: object, field: str, depth: int = 0) -> object:
    if depth > 8:
        raise ValueError(f"{field} exceeds maximum depth")
    if value is None or isinstance(value, (str, bool)):
        if isinstance(value, str) and len(value) > 4_000:
            raise ValueError(f"{field} is too long")
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > 9_007_199_254_740_991:
            raise ValueError(f"{field} exceeds safe integer range")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field} must be finite")
        return value
    if isinstance(value, list):
        maximum = 500 if field.endswith(".existingFingerprints") else 100
        if len(value) > maximum:
            raise ValueError(f"{field} has too many items")
        return [
            _assert_bounded_json(item, f"{field}[{index}]", depth + 1)
            for index, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        if len(value) > 80 or any(not isinstance(key, str) for key in value):
            raise ValueError(f"{field} has invalid fields")
        return {
            key: _assert_bounded_json(item, f"{field}.{key}", depth + 1)
            for key, item in value.items()
        }
    raise ValueError(f"{field} contains an unsupported value")


def _nullable_sha256(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("Provider request hash is invalid")
    return value


def _nullable_safe_integer(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= 2_147_483_647:
        raise ValueError("token usage is invalid")
    return value


def _billing_evidence(value: object, input_tokens: object, output_tokens: object) -> Literal["reported", "unknown"]:
    expected = "reported" if input_tokens is not None or output_tokens is not None else "unknown"
    if value != expected:
        raise ValueError("billing evidence is not derived from token usage")
    return expected


class OpenMaicQuestionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = str(code or "generation_failed")
        self.message = str(message or "OpenMAIC question generation failed")


@dataclass(frozen=True)
class QuestionCandidateResult:
    request_id: str
    candidate_course: dict[str, Any]
    question_fingerprints: tuple[str, ...]
    validation: dict[str, Any]
    provider: str
    model: str
    elapsed_ms: int


@dataclass(frozen=True)
class IndependentSolutionResult:
    request_id: str
    solution: dict[str, Any]
    provider: str
    model: str
    elapsed_ms: int


class OpenMaicQuestionAdapter:
    """Isolated OpenMAIC/Kimi question generation and fresh-answer verification."""

    def __init__(
        self,
        *,
        sidecar_root: str | Path | None = None,
        node_binary: str = "node",
        timeout_seconds: float = 420.0,
        provider_name: str | None = None,
        model_name: str | None = None,
        base_url: str | None = None,
        api_key_env: str = "APP_AI_API_KEY",
        provider_timeout_ms: int = 90_000,
        max_tokens: int = 8_000,
        temperature: float = 0.2,
        fake_mode: bool = False,
        generation_fake_responses: Sequence[str] | None = None,
        verification_fake_responses: Sequence[str] | None = None,
        consistency_repair_fake_responses: Sequence[str] | None = None,
        process_runner=subprocess.run,
    ):
        backend_root = Path(__file__).resolve().parents[1]
        self.sidecar_root = Path(
            sidecar_root or backend_root / "openmaic-sidecar"
        ).resolve()
        self.node_binary = str(node_binary)
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.provider_name = (
            provider_name or os.getenv("APP_AI_PROVIDER") or "kimi"
        ).strip()
        self.model_name = (model_name or os.getenv("APP_AI_MODEL") or "").strip()
        self.base_url = (base_url or os.getenv("APP_AI_BASE_URL") or "").strip()
        self.api_key_env = str(api_key_env).strip()
        self.provider_timeout_ms = int(provider_timeout_ms)
        self.max_tokens = int(max_tokens)
        self.temperature = float(temperature)
        self.fake_mode = bool(fake_mode)
        self.generation_fake_responses = list(generation_fake_responses or [])
        self.verification_fake_responses = list(verification_fake_responses or [])
        self.consistency_repair_fake_responses = list(
            consistency_repair_fake_responses or []
        )
        self._run = process_runner

    @property
    def cli_path(self) -> Path:
        return self.sidecar_root / "src" / "cli.mjs"

    def availability(self) -> dict[str, Any]:
        if not self.cli_path.is_file() or shutil.which(self.node_binary) is None:
            return {
                "available": False,
                "generator": "openmaic",
                "reason": "OpenMAIC question sidecar is unavailable",
            }
        try:
            completed = self._run_process(
                [self.node_binary, str(self.cli_path), "--availability"]
            )
            payload = self._parse(completed.stdout)
        except (OSError, subprocess.TimeoutExpired, OpenMaicQuestionError) as exc:
            return {
                "available": False,
                "generator": "openmaic",
                "reason": str(exc),
            }
        supported = payload.get("supportedContracts")
        contracts = supported if isinstance(supported, list) else []
        contract_inputs = {
            str(item.get("input")) for item in contracts if isinstance(item, Mapping)
        }
        runtime_available = bool(payload.get("available")) and {
            QUESTION_GENERATION_INPUT_SCHEMA,
            QUESTION_VERIFICATION_INPUT_SCHEMA,
            QUESTION_CONSISTENCY_REPAIR_INPUT_SCHEMA,
        }.issubset(contract_inputs)
        provider_configured = self.fake_mode or bool(
            self.model_name
            and self.base_url
            and os.getenv(self.api_key_env, "").strip()
        )
        return {
            "available": runtime_available and provider_configured,
            "runtimeAvailable": runtime_available,
            "providerConfigured": provider_configured,
            "generator": "openmaic",
            "provider": self.provider_name,
            "model": self.model_name,
            "supportedContracts": contracts,
            "reason": None
            if runtime_available and provider_configured
            else str(payload.get("reason") or "OpenMAIC provider is not configured"),
        }

    def generate(
        self,
        *,
        request_id: str,
        grade_code: str,
        subject: str,
        skill_boundary: Mapping[str, Any],
        existing_question_fingerprints: Sequence[str] = (),
        generation_feedback: Mapping[str, str] | None = None,
    ) -> QuestionCandidateResult:
        payload = {
            "schemaVersion": QUESTION_GENERATION_INPUT_SCHEMA,
            "requestId": str(request_id),
            "gradeCode": str(grade_code),
            "subject": str(subject),
            "skillBoundary": dict(skill_boundary),
            "questionCount": 5,
            "existingFingerprints": list(existing_question_fingerprints),
            **(
                {"generationFeedback": dict(generation_feedback)}
                if generation_feedback
                else {}
            ),
            **self._execution_payload(self.generation_fake_responses),
        }
        response, elapsed = self._call(payload)
        self._require_envelope(
            response,
            schema=QUESTION_CANDIDATES_OUTPUT_SCHEMA,
            request_id=request_id,
        )
        course = response.get("candidateCourse")
        fingerprints = response.get("questionFingerprints")
        validation = response.get("validation")
        if not isinstance(course, dict) or not isinstance(fingerprints, list):
            raise OpenMaicQuestionError(
                "invalid_response", "OpenMAIC returned an incomplete candidate course"
            )
        questions = (course.get("content") or {}).get("questions")
        if not isinstance(questions, list) or len(questions) != len(fingerprints):
            raise OpenMaicQuestionError(
                "invalid_response", "OpenMAIC returned mismatched question fingerprints"
            )
        normalized_fingerprints: list[str] = []
        for index, item in enumerate(fingerprints):
            fingerprint = str(
                item.get("fingerprint") if isinstance(item, Mapping) else ""
            ).strip().lower()
            if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
                raise OpenMaicQuestionError(
                    "invalid_response", "OpenMAIC returned an invalid question fingerprint"
                )
            question = questions[index]
            question_id = str(
                item.get("questionId") if isinstance(item, Mapping) else ""
            )
            if not isinstance(question, Mapping) or question_id != str(
                question.get("id") or ""
            ):
                raise OpenMaicQuestionError(
                    "invalid_response", "OpenMAIC returned a mismatched question fingerprint"
                )
            recomputed = DynamicLearningCourseRepository.question_fingerprint(
                grade_code=str(grade_code),
                subject=str(subject),
                node_code=str(skill_boundary.get("skillId") or ""),
                question=question,
            )
            if fingerprint != recomputed:
                raise OpenMaicQuestionError(
                    "invalid_response", "OpenMAIC question fingerprint verification failed"
                )
            normalized_fingerprints.append(fingerprint)
        return QuestionCandidateResult(
            request_id=str(request_id),
            candidate_course=course,
            question_fingerprints=tuple(normalized_fingerprints),
            validation=dict(validation) if isinstance(validation, Mapping) else {},
            provider=str(response.get("provider") or self.provider_name),
            model=str(response.get("model") or self.model_name),
            elapsed_ms=max(int(response.get("elapsedMs") or elapsed), 0),
        )

    def verify(
        self,
        *,
        request_id: str,
        grade_code: str,
        subject: str,
        skill_boundary: Mapping[str, Any],
        candidate_course: Mapping[str, Any],
    ) -> IndependentSolutionResult:
        content = candidate_course.get("content")
        questions = content.get("questions") if isinstance(content, Mapping) else None
        if not isinstance(questions, list):
            raise OpenMaicQuestionError(
                "invalid_input", "candidate course does not contain questions"
            )
        public_questions: list[dict[str, Any]] = []
        for item in questions:
            if not isinstance(item, Mapping):
                raise OpenMaicQuestionError("invalid_input", "question must be an object")
            public = {
                "id": item.get("id"),
                "type": item.get("type"),
                "prompt": item.get("prompt"),
            }
            if item.get("type") in {"single_choice", "sequence"}:
                choices = item.get("choices")
                if not isinstance(choices, list):
                    raise OpenMaicQuestionError(
                        "invalid_input", "choice question must contain choices"
                    )
                public["choices"] = [
                    {"id": choice.get("id"), "label": choice.get("label")}
                    for choice in choices
                    if isinstance(choice, Mapping)
                ]
                if len(public["choices"]) != len(choices):
                    raise OpenMaicQuestionError(
                        "invalid_input", "choice must be an object"
                    )
            public_questions.append(public)
        public_teaching_flow = self._public_teaching_flow(
            content.get("teachingFlow") if isinstance(content, Mapping) else None,
            public_questions=public_questions,
            candidate_questions=questions,
        )
        payload = {
            "schemaVersion": QUESTION_VERIFICATION_INPUT_SCHEMA,
            "requestId": str(request_id),
            "gradeCode": str(grade_code),
            "subject": str(subject),
            "skillBoundary": dict(skill_boundary),
            "publicQuestions": public_questions,
            "publicTeachingFlow": public_teaching_flow,
            **self._execution_payload(self.verification_fake_responses),
        }
        response, elapsed = self._call(payload)
        self._require_envelope(
            response,
            schema=QUESTION_VERIFICATION_OUTPUT_SCHEMA,
            request_id=request_id,
        )
        solution = response.get("solution")
        if not isinstance(solution, dict):
            raise OpenMaicQuestionError(
                "invalid_response", "OpenMAIC returned no independent solution"
            )
        teaching_review = solution.get("teachingReview")
        if (
            not isinstance(teaching_review, Mapping)
            or not isinstance(teaching_review.get("passed"), bool)
            or not isinstance(teaching_review.get("issues"), list)
        ):
            raise OpenMaicQuestionError(
                "invalid_response",
                "OpenMAIC returned no independent teaching review",
            )
        return IndependentSolutionResult(
            request_id=str(request_id),
            solution=solution,
            provider=str(response.get("provider") or self.provider_name),
            model=str(response.get("model") or self.model_name),
            elapsed_ms=max(int(response.get("elapsedMs") or elapsed), 0),
        )

    def repair_consistency(
        self,
        *,
        request_id: str,
        grade_code: str,
        subject: str,
        skill_boundary: Mapping[str, Any],
        candidate_course: Mapping[str, Any],
        review_issues: Sequence[str],
    ) -> QuestionCandidateResult:
        """Repair public teaching copy once while keeping question authority frozen."""

        content = candidate_course.get("content")
        questions = content.get("questions") if isinstance(content, Mapping) else None
        if not isinstance(content, Mapping) or not isinstance(questions, list):
            raise OpenMaicQuestionError(
                "invalid_input", "candidate course does not contain questions"
            )
        public_questions: list[dict[str, Any]] = []
        public_guidance: list[dict[str, str]] = []
        for item in questions:
            if not isinstance(item, Mapping):
                raise OpenMaicQuestionError("invalid_input", "question must be an object")
            question_id = str(item.get("id") or "")
            question_type = str(item.get("type") or "")
            prompt = item.get("prompt")
            hint = item.get("hint")
            explanation = item.get("explanation")
            if (
                not question_id
                or not isinstance(prompt, str)
                or not isinstance(hint, str)
                or not isinstance(explanation, str)
            ):
                raise OpenMaicQuestionError(
                    "invalid_input", "candidate question public text is incomplete"
                )
            public: dict[str, Any] = {
                "id": question_id,
                "type": question_type,
                "prompt": prompt,
            }
            if question_type in {"single_choice", "sequence"}:
                choices = item.get("choices")
                if not isinstance(choices, list):
                    raise OpenMaicQuestionError(
                        "invalid_input", "choice question must contain choices"
                    )
                public["choices"] = [
                    {"id": choice.get("id"), "label": choice.get("label")}
                    for choice in choices
                    if isinstance(choice, Mapping)
                ]
                if len(public["choices"]) != len(choices):
                    raise OpenMaicQuestionError(
                        "invalid_input", "choice must be an object"
                    )
            public_questions.append(public)
            public_guidance.append(
                {
                    "questionId": question_id,
                    "hint": hint,
                    "explanation": explanation,
                }
            )
        title = candidate_course.get("title")
        intro = content.get("intro")
        issues = [str(item).strip() for item in review_issues if str(item).strip()]
        if (
            len(public_questions) != 5
            or not isinstance(title, str)
            or not title.strip()
            or not isinstance(intro, str)
            or not intro.strip()
            or len(issues) < 1
            or len(issues) > 3
        ):
            raise OpenMaicQuestionError(
                "invalid_input", "consistency repair input is incomplete"
            )
        public_teaching_flow = self._public_teaching_flow(
            content.get("teachingFlow"),
            public_questions=public_questions,
            candidate_questions=questions,
        )
        payload = {
            "schemaVersion": QUESTION_CONSISTENCY_REPAIR_INPUT_SCHEMA,
            "requestId": str(request_id),
            "gradeCode": str(grade_code),
            "subject": str(subject),
            "skillBoundary": dict(skill_boundary),
            "publicLessonText": {"title": title, "intro": intro},
            "publicQuestions": public_questions,
            "publicTeachingFlow": public_teaching_flow,
            "publicGuidance": public_guidance,
            "reviewIssues": issues,
            **self._execution_payload(self.consistency_repair_fake_responses),
        }
        response, elapsed = self._call(payload)
        self._require_envelope(
            response,
            schema=QUESTION_CONSISTENCY_REPAIR_OUTPUT_SCHEMA,
            request_id=request_id,
        )
        repair = response.get("repair")
        if not isinstance(repair, Mapping) or set(repair) != {
            "title",
            "intro",
            "teach",
            "recap",
            "questionGuidance",
        }:
            raise OpenMaicQuestionError(
                "invalid_response", "OpenMAIC returned an invalid consistency repair"
            )
        guidance = repair.get("questionGuidance")
        question_ids = [str(item["id"]) for item in public_questions]
        if (
            not isinstance(guidance, list)
            or len(guidance) != len(question_ids)
            or any(
                not isinstance(item, Mapping)
                or set(item) != {"questionId", "hint", "explanation"}
                or str(item.get("questionId") or "") != question_ids[index]
                or not isinstance(item.get("hint"), str)
                or not isinstance(item.get("explanation"), str)
                for index, item in enumerate(guidance)
            )
        ):
            raise OpenMaicQuestionError(
                "invalid_response", "OpenMAIC repair changed question identity"
            )

        repaired = copy.deepcopy(dict(candidate_course))
        repaired_content = repaired["content"]
        repaired_flow = repaired_content["teachingFlow"]
        repaired["title"] = str(repair["title"])
        repaired_content["intro"] = str(repair["intro"])
        repaired_flow["teach"] = copy.deepcopy(dict(repair["teach"]))
        repaired_flow["recap"] = copy.deepcopy(dict(repair["recap"]))
        for question, text in zip(repaired_content["questions"], guidance):
            question["hint"] = str(text["hint"])
            question["explanation"] = str(text["explanation"])

        fingerprints = tuple(
            DynamicLearningCourseRepository.question_fingerprint(
                grade_code=str(grade_code),
                subject=str(subject),
                node_code=str(skill_boundary.get("skillId") or ""),
                question=question,
            )
            for question in repaired_content["questions"]
        )
        return QuestionCandidateResult(
            request_id=str(request_id),
            candidate_course=repaired,
            question_fingerprints=fingerprints,
            validation={"schemaValidated": True, "consistencyRepairApplied": True},
            provider=str(response.get("provider") or self.provider_name),
            model=str(response.get("model") or self.model_name),
            elapsed_ms=max(int(response.get("elapsedMs") or elapsed), 0),
        )

    @staticmethod
    def _public_teaching_flow(
        raw: object,
        *,
        public_questions: Sequence[Mapping[str, Any]],
        candidate_questions: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        if not isinstance(raw, Mapping) or set(raw) != {
            "schemaVersion",
            "teach",
            "demoQuestionId",
            "guidedQuestionIds",
            "independentQuestionIds",
            "recap",
        }:
            raise OpenMaicQuestionError(
                "invalid_input", "candidate course does not contain a valid teaching flow"
            )
        teach = raw.get("teach")
        recap = raw.get("recap")
        if (
            raw.get("schemaVersion") != TEACHING_FLOW_SCHEMA_VERSION
            or not isinstance(teach, Mapping)
            or set(teach) != {"title", "sayText", "keyPoints"}
            or not isinstance(recap, Mapping)
            or set(recap) != {"sayText"}
            or not isinstance(teach.get("keyPoints"), list)
        ):
            raise OpenMaicQuestionError(
                "invalid_input", "candidate course does not contain a valid teaching flow"
            )
        question_ids = [str(item.get("id") or "") for item in public_questions]
        guided_ids = raw.get("guidedQuestionIds")
        independent_ids = raw.get("independentQuestionIds")
        demo_explanation = (
            candidate_questions[0].get("explanation")
            if len(candidate_questions) == 5
            and isinstance(candidate_questions[0], Mapping)
            else None
        )
        if (
            len(question_ids) != 5
            or str(raw.get("demoQuestionId") or "") != question_ids[0]
            or not isinstance(guided_ids, list)
            or [str(item) for item in guided_ids] != question_ids[1:3]
            or not isinstance(independent_ids, list)
            or [str(item) for item in independent_ids] != question_ids[3:5]
            or not isinstance(demo_explanation, str)
            or not demo_explanation.strip()
        ):
            raise OpenMaicQuestionError(
                "invalid_input", "candidate teaching flow does not cover its questions"
            )
        return {
            "schemaVersion": TEACHING_FLOW_SCHEMA_VERSION,
            "teach": {
                "title": teach.get("title"),
                "sayText": teach.get("sayText"),
                "keyPoints": list(teach["keyPoints"]),
            },
            "demoQuestionId": question_ids[0],
            "workedExample": {
                "questionId": question_ids[0],
                "explanation": demo_explanation.strip(),
            },
            "guidedQuestionIds": question_ids[1:3],
            "independentQuestionIds": question_ids[3:5],
            "recap": {"sayText": recap.get("sayText")},
        }

    def _execution_payload(self, fake_responses: Sequence[str]) -> dict[str, Any]:
        return {
            "mode": "fake" if self.fake_mode else "live",
            "provider": {
                "name": self.provider_name,
                "model": self.model_name,
                "baseUrl": self.base_url,
                "apiKeyEnv": self.api_key_env,
                "timeoutMs": self.provider_timeout_ms,
                "maxTokens": self.max_tokens,
                "temperature": self.temperature,
            },
            **({"fakeResponses": list(fake_responses)} if self.fake_mode else {}),
        }

    def _call(self, payload: Mapping[str, Any]) -> tuple[dict[str, Any], int]:
        if not self.cli_path.is_file() or shutil.which(self.node_binary) is None:
            raise OpenMaicQuestionError(
                "openmaic_unavailable", "OpenMAIC question sidecar is unavailable"
            )
        started = time.monotonic()
        try:
            completed = self._run_process(
                [self.node_binary, str(self.cli_path)],
                input_text=json.dumps(payload, ensure_ascii=False),
                fake_mode=self.fake_mode,
            )
        except subprocess.TimeoutExpired as exc:
            raise OpenMaicQuestionError(
                "openmaic_timeout",
                f"OpenMAIC question request timed out after {self.timeout_seconds:g}s",
            ) from exc
        except OSError as exc:
            raise OpenMaicQuestionError(
                "openmaic_unavailable", "OpenMAIC question sidecar could not start"
            ) from exc
        response = self._parse(completed.stdout)
        if completed.returncode != 0:
            error = response.get("error")
            raise OpenMaicQuestionError(
                str(error.get("code") if isinstance(error, Mapping) else "generation_failed"),
                str(
                    error.get("message")
                    if isinstance(error, Mapping)
                    else "OpenMAIC question generation failed"
                ),
            )
        return response, int((time.monotonic() - started) * 1000)

    def _run_process(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        fake_mode: bool = False,
    ):
        environment = os.environ.copy()
        if fake_mode:
            environment["OPENMAIC_FAKE_MODE"] = "1"
        return self._run(
            args,
            cwd=str(self.sidecar_root),
            input=input_text,
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            env=environment,
            check=False,
        )

    @staticmethod
    def _parse(raw: object) -> dict[str, Any]:
        try:
            payload = json.loads(str(raw or ""))
        except json.JSONDecodeError as exc:
            raise OpenMaicQuestionError(
                "invalid_response", "OpenMAIC sidecar returned invalid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise OpenMaicQuestionError(
                "invalid_response", "OpenMAIC sidecar returned a non-object response"
            )
        return payload

    @staticmethod
    def _require_envelope(
        payload: Mapping[str, Any], *, schema: str, request_id: str
    ) -> None:
        if payload.get("schemaVersion") != schema:
            raise OpenMaicQuestionError(
                "invalid_response", "OpenMAIC returned an unsupported response schema"
            )
        if str(payload.get("requestId") or "") != str(request_id):
            raise OpenMaicQuestionError(
                "invalid_response", "OpenMAIC response requestId does not match"
            )
        if payload.get("generator") != "openmaic":
            raise OpenMaicQuestionError(
                "invalid_response", "OpenMAIC response generator identity is invalid"
            )
