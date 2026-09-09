from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Mapping, Sequence

from core.database import Database, DatabaseConnection, DatabaseRow
from services.learning_question_phase_contract import provider_phase


_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b([a-z0-9_.-]*(?:api[_-]?key|token|secret|password)[a-z0-9_.-]*)"
    r"\s*[:=]\s*([^\s,;]+)"
)
_BEARER_TOKEN = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
_URL_CREDENTIALS = re.compile(r"(https?://)([^\s/@:]+):([^\s/@]+)@", re.I)
_PROVIDER_TOKEN = re.compile(r"\b(?:sk|ak)-[A-Za-z0-9_-]{8,}\b")
_DISPATCH_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:@/+-]{1,128}$")
_SAFE_DISPATCH_CODE = re.compile(r"^[a-z0-9_]{1,128}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_AMBIGUOUS_DISPATCH_CODES = frozenset(
    {
        "provider_timeout",
        "provider_connection_interrupted",
        "provider_response_lost",
        "provider_outcome_unknown",
    }
)
_FAILED_SAFE_DISPATCH_CODES = frozenset(
    {
        "question_phase_invalid_input",
        "question_phase_contract_drift",
        "question_phase_unsupported",
        "question_phase_preflight_rejected",
        "question_phase_output_rejected",
        "question_phase_json_rejected",
        "question_phase_verification_json_rejected",
        "question_phase_verification_answers_rejected",
        "question_phase_verification_numeric_rejected",
        "question_phase_verification_review_rejected",
        "question_phase_verification_semantic_rejected",
        "question_phase_verification_checkpoint_rejected",
        "provider_unavailable",
        "provider_request_rejected",
        "provider_no_candidate",
        "provider_invalid_response",
        "phase_deadline_insufficient",
        "phase_lease_lost",
    }
)


@dataclass(frozen=True)
class ProviderDispatchReservation:
    dispatch: Mapping[str, object]
    created: bool


def _canonical_dispatch_json(value: Mapping[str, object]) -> str:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _dispatch_id_for(
    build_item_id: str, logical_attempt: int, phase: str, phase_ordinal: int
) -> str:
    identity = f"{build_item_id}:{logical_attempt}:{phase}:{phase_ordinal}"
    return (
        "learning_provider_dispatch_"
        + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:48]
    )


def _validate_strict_reservation_request(
    *,
    phase: str,
    phase_ordinal: int,
    generation_request_id: str,
    provider: str,
    model: str,
    profile: str,
    input_sha256: str,
    command_checkpoint: Mapping[str, object],
    prepared_request: Mapping[str, object],
) -> None:
    expected_keys = {
        "schemaVersion", "questionContractVersion", "requestId", "phase",
        "phaseOrdinal", "gradeCode", "subject", "instructionLanguageCode",
        "targetLanguageCode", "skillBoundary", "checkpoint", "provider",
        "mode", "fakeResponses",
    }
    if set(prepared_request) != expected_keys:
        raise ValueError("provider dispatch prepared request fields mismatch")
    if (
        prepared_request.get("requestId") != generation_request_id
        or prepared_request.get("phase") != phase
        or type(prepared_request.get("phaseOrdinal")) is not int
        or prepared_request.get("phaseOrdinal") != phase_ordinal
        or prepared_request.get("mode") != "live"
        or prepared_request.get("fakeResponses") != []
    ):
        raise ValueError("provider dispatch prepared request identity mismatch")
    checkpoint = prepared_request.get("checkpoint")
    if not isinstance(checkpoint, Mapping) or _canonical_dispatch_json(
        checkpoint
    ) != _canonical_dispatch_json(command_checkpoint):
        raise ValueError("provider dispatch command checkpoint mismatch")
    request_json = _canonical_dispatch_json(prepared_request)
    if hashlib.sha256(request_json.encode("utf-8")).hexdigest() != input_sha256:
        raise ValueError("provider dispatch input hash mismatch")
    profile_value = prepared_request.get("provider")
    if not isinstance(profile_value, Mapping):
        raise ValueError("provider dispatch profile is invalid")
    if profile_value.get("name") != provider or profile_value.get("model") != model:
        raise ValueError("provider dispatch Provider identity mismatch")
    profile_json = _canonical_dispatch_json(profile_value)
    if hashlib.sha256(profile_json.encode("utf-8")).hexdigest() != profile:
        raise ValueError("provider dispatch profile hash mismatch")


def _strict_item_matches(
    item: Mapping[str, object] | None,
    *,
    grade_code: str,
    subject: str,
    skill_id: str,
    logical_attempt: int,
    phase: str,
    generation_request_id: str,
    item_lease_token: str,
    attempt_started_at: int,
    attempt_hard_deadline_at: int,
    work_unit_deadline_at: int,
    lease_expires_at: int,
) -> bool:
    return bool(
        item is not None
        and str(item.get("execution_mode_snapshot") or "") == "content_only"
        and str(item.get("grade_code") or "") == grade_code
        and str(item.get("subject") or "") == subject
        and str(item.get("skill_id") or "") == skill_id
        and str(item.get("status") or "") == "processing"
        and int(item.get("attempt_count") or 0) == logical_attempt
        and int(item.get("content_claim_attempt_ordinal") or 0) == logical_attempt
        and str(item.get("content_phase") or "") == phase
        and str(item.get("active_generation_request_id") or "")
        == generation_request_id
        and str(item.get("content_lease_token") or "") == item_lease_token
        and item.get("content_attempt_started_at") is not None
        and int(item["content_attempt_started_at"]) == attempt_started_at
        and item.get("content_provider_attempt_hard_deadline_at") is not None
        and int(item["content_provider_attempt_hard_deadline_at"])
        == attempt_hard_deadline_at
        and item.get("content_work_unit_deadline_at") is not None
        and int(item["content_work_unit_deadline_at"]) == work_unit_deadline_at
        and item.get("content_lease_expires_at") is not None
        and int(item["content_lease_expires_at"]) == lease_expires_at
    )


def _transition_for_phase(
    transitions: Sequence[Mapping[str, object]], phase: str
) -> Mapping[str, object]:
    for transition in transitions:
        if transition.get("phase") == phase:
            return transition
    raise ValueError("provider dispatch transition authority is missing")


def _source_artifact(
    normalized_by_phase: Mapping[str, Mapping[str, object]],
    artifact: Mapping[str, object],
) -> object:
    sources = artifact.get("sources")
    if not isinstance(sources, tuple):
        raise ValueError("provider dispatch predecessor sources are invalid")
    ordered = sorted(
        (source for source in sources if isinstance(source, Mapping)),
        key=lambda source: int(source.get("phaseOrdinal") or 0),
        reverse=True,
    )
    for source in ordered:
        phase = str(source.get("phase") or "")
        checkpoint = normalized_by_phase.get(phase)
        if checkpoint is None:
            continue
        if checkpoint.get("phaseStatus") != source.get("phaseStatus"):
            continue
        output_key = str(source.get("outputKey") or "")
        if output_key not in checkpoint:
            continue
        return checkpoint[output_key]
    raise ValueError("provider dispatch predecessor artifact is missing")


def _phase_input_checkpoint(
    *,
    phase: str,
    input_keys: Sequence[str],
    transition: Mapping[str, object],
    normalized_by_phase: Mapping[str, Mapping[str, object]],
    attempt_initial_checkpoint: Mapping[str, object],
) -> dict[str, object]:
    artifacts = transition.get("requiredSucceededArtifacts")
    if not isinstance(artifacts, tuple):
        raise ValueError("provider dispatch transition artifacts are invalid")
    artifact_by_key = {
        str(artifact.get("currentInputKey") or ""): artifact
        for artifact in artifacts
        if isinstance(artifact, Mapping)
    }
    result: dict[str, object] = {}
    for key in input_keys:
        if key == "questionCount":
            result[key] = attempt_initial_checkpoint["questionCount"]
        elif key == "existingFingerprints":
            result[key] = list(attempt_initial_checkpoint["existingFingerprints"])
        elif key == "generationFeedback":
            result[key] = attempt_initial_checkpoint["generationFeedback"]
        elif key in artifact_by_key:
            result[key] = _source_artifact(
                normalized_by_phase, artifact_by_key[key]
            )
        elif key == "leakingQuestionIndexes":
            from integrations.openmaic_question_adapter import _practice_leak_indexes

            lesson = result.get("lessonText")
            reconciliation = result.get("reconciliation")
            if not isinstance(lesson, Mapping) or not isinstance(reconciliation, Mapping):
                raise ValueError("provider dispatch leak predecessor is missing")
            flow = lesson.get("teachingFlow")
            questions = reconciliation.get("questions")
            if not isinstance(flow, Mapping) or not isinstance(questions, list):
                raise ValueError("provider dispatch leak predecessor is invalid")
            result[key] = _practice_leak_indexes(flow, questions)
        elif key == "violatingQuestionIndexes":
            from integrations.openmaic_question_adapter import _choice_prompt_violation_indexes

            reconciliation = result.get("reconciliation")
            questions = reconciliation.get("questions") if isinstance(reconciliation, Mapping) else None
            if not isinstance(questions, list):
                raise ValueError("provider dispatch choice predecessor is invalid")
            result[key] = _choice_prompt_violation_indexes(questions)
        elif key == "reviewIssues":
            solution = result.get("independentSolution")
            review = solution.get("teachingReview") if isinstance(solution, Mapping) else None
            issues = review.get("issues") if isinstance(review, Mapping) else None
            if not isinstance(issues, list):
                raise ValueError("provider dispatch review predecessor is invalid")
            result[key] = list(issues)
        else:
            raise ValueError(
                f"provider dispatch cannot reconstruct predecessor input {phase}.{key}"
            )
    return result


def _normalize_locked_predecessors(
    rows: Sequence[Mapping[str, object]],
    *,
    prepared_request: Mapping[str, object],
    logical_attempt: int,
    generation_request_id: str,
    provider: str,
    model: str,
    profile: str,
    attempt_initial_checkpoint: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    from integrations.openmaic_question_adapter import (
        PreparedQuestionPhase,
        QuestionPhaseCommand,
        QUESTION_PHASE_IO,
        QUESTION_PHASE_TRANSITIONS,
        _normalize_phase_checkpoint,
        _normalize_phase_output_checkpoint,
    )

    normalized: dict[str, Mapping[str, object]] = {}
    current_checkpoint = prepared_request.get("checkpoint")
    if not isinstance(current_checkpoint, Mapping):
        raise ValueError("provider dispatch current checkpoint is invalid")
    boundary = prepared_request.get("skillBoundary")
    provider_profile = prepared_request.get("provider")
    if not isinstance(boundary, Mapping) or not isinstance(provider_profile, Mapping):
        raise ValueError("provider dispatch stable request profile is invalid")
    for row in rows:
        if (
            int(row.get("logical_attempt") or 0) != logical_attempt
            or str(row.get("generation_request_id") or "") != generation_request_id
            or str(row.get("provider") or "") != provider
            or str(row.get("model") or "") != model
            or str(row.get("profile") or "") != profile
            or str(row.get("status") or "") != "succeeded"
        ):
            raise ValueError("provider dispatch predecessor identity is invalid")
        phase = str(row.get("phase") or "")
        ordinal = int(row.get("phase_ordinal") or 0)
        io = next(
            (
                item
                for item in QUESTION_PHASE_IO
                if item.get("phase") == phase
                and item.get("phaseOrdinal") == ordinal
            ),
            None,
        )
        if io is None:
            raise ValueError("provider dispatch predecessor phase is invalid")
        raw_json = row.get("checkpoint_json")
        if not isinstance(raw_json, str):
            raise ValueError("provider dispatch predecessor checkpoint is missing")
        try:
            raw_checkpoint = json.loads(raw_json)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("provider dispatch predecessor checkpoint is invalid") from exc
        if not isinstance(raw_checkpoint, Mapping):
            raise ValueError("provider dispatch predecessor checkpoint is invalid")
        canonical = _canonical_dispatch_json(raw_checkpoint)
        if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != row.get("output_sha256"):
            raise ValueError("provider dispatch predecessor output hash drift")
        transition = _transition_for_phase(QUESTION_PHASE_TRANSITIONS, phase)
        input_keys = io.get("inputCheckpointKeys")
        if not isinstance(input_keys, tuple):
            raise ValueError("provider dispatch predecessor input authority is invalid")
        reconstructed = _phase_input_checkpoint(
            phase=phase,
            input_keys=input_keys,
            transition=transition,
            normalized_by_phase=normalized,
            attempt_initial_checkpoint=attempt_initial_checkpoint,
        )
        command = QuestionPhaseCommand(
            build_item_id=str(row.get("build_item_id") or ""),
            logical_attempt=logical_attempt,
            phase=phase,
            phase_ordinal=ordinal,
            generation_request_id=generation_request_id,
            grade_code=str(prepared_request.get("gradeCode") or ""),
            subject=str(prepared_request.get("subject") or ""),
            instruction_language_code=str(prepared_request.get("instructionLanguageCode") or ""),
            target_language_code=str(prepared_request.get("targetLanguageCode") or ""),
            boundary=boundary,
            checkpoint=reconstructed,
        )
        normalized_input = _normalize_phase_checkpoint(
            command,
            io,
            reconstructed,
            provider=provider_profile,
        )
        request = dict(prepared_request)
        request["phase"] = phase
        request["phaseOrdinal"] = ordinal
        request["checkpoint"] = normalized_input
        request_json = _canonical_dispatch_json(request)
        if hashlib.sha256(request_json.encode("utf-8")).hexdigest() != row.get(
            "input_sha256"
        ):
            raise ValueError("provider dispatch predecessor input hash drift")
        profile_json = _canonical_dispatch_json(provider_profile)
        prepared = PreparedQuestionPhase(
            command=command,
            request=request,
            canonical_input_json=request_json,
            input_sha256=hashlib.sha256(request_json.encode("utf-8")).hexdigest(),
            provider=provider_profile,
            canonical_profile_json=profile_json,
            profile_sha256=hashlib.sha256(profile_json.encode("utf-8")).hexdigest(),
        )
        normalized_output = _normalize_phase_output_checkpoint(prepared, raw_checkpoint)
        if _canonical_dispatch_json(raw_checkpoint) != _canonical_dispatch_json(normalized_output):
            raise ValueError("provider dispatch predecessor checkpoint is not normalized")
        normalized[phase] = normalized_output
    return normalized


def _verify_current_transition(
    *,
    phase: str,
    prepared_request: Mapping[str, object],
    normalized_by_phase: Mapping[str, Mapping[str, object]],
) -> None:
    from integrations.openmaic_question_adapter import QUESTION_PHASE_TRANSITIONS

    transition = _transition_for_phase(QUESTION_PHASE_TRANSITIONS, phase)
    artifacts = transition.get("requiredSucceededArtifacts")
    checkpoint = prepared_request.get("checkpoint")
    if not isinstance(artifacts, tuple) or not isinstance(checkpoint, Mapping):
        raise ValueError("provider dispatch current transition is invalid")
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            raise ValueError("provider dispatch transition artifact is invalid")
        key = str(artifact.get("currentInputKey") or "")
        if key not in checkpoint:
            raise ValueError("provider dispatch current artifact is missing")
        expected = _source_artifact(normalized_by_phase, artifact)
        actual = checkpoint[key]
        if _canonical_dispatch_json({"value": expected}) != _canonical_dispatch_json({"value": actual}):
            raise ValueError("provider dispatch predecessor artifact provenance mismatch")


def _verify_phase_14_inventory_proof(
    *,
    prepared_request: Mapping[str, object],
    normalized_by_phase: Mapping[str, Mapping[str, object]],
    predecessor_rows: Sequence[Mapping[str, object]],
) -> None:
    from integrations.openmaic_question_adapter import (
        QUESTION_PHASE_IO,
        QUESTION_PHASE_TRANSITIONS,
        _normalize_phase_checkpoint,
    )

    phase_11_row = next(
        (row for row in predecessor_rows if row.get("phase") == "independent_verification"),
        None,
    )
    if phase_11_row is None:
        raise ValueError("phase 11 predecessor is missing for phase 14 inventory proof")
    checkpoint = prepared_request.get("checkpoint")
    provider_profile = prepared_request.get("provider")
    boundary = prepared_request.get("skillBoundary")
    if not isinstance(checkpoint, Mapping) or not isinstance(provider_profile, Mapping) or not isinstance(boundary, Mapping):
        raise ValueError("phase 14 inventory authority is invalid")
    inventory = checkpoint.get("existingFingerprints")
    if not isinstance(inventory, list):
        raise ValueError("phase 14 originality inventory is invalid")
    io = next(item for item in QUESTION_PHASE_IO if item.get("phaseOrdinal") == 11)
    transition = _transition_for_phase(QUESTION_PHASE_TRANSITIONS, "independent_verification")
    input_keys = io.get("inputCheckpointKeys")
    assert isinstance(input_keys, tuple)
    reconstructed = _phase_input_checkpoint(
        phase="independent_verification",
        input_keys=input_keys,
        transition=transition,
        normalized_by_phase=normalized_by_phase,
        attempt_initial_checkpoint={
            "questionCount": 5,
            "existingFingerprints": inventory,
            "generationFeedback": None,
        },
    )
    from integrations.openmaic_question_adapter import QuestionPhaseCommand

    command = QuestionPhaseCommand(
        build_item_id=str(phase_11_row.get("build_item_id") or ""),
        logical_attempt=int(phase_11_row.get("logical_attempt") or 0),
        phase="independent_verification",
        phase_ordinal=11,
        generation_request_id=str(phase_11_row.get("generation_request_id") or ""),
        grade_code=str(prepared_request.get("gradeCode") or ""),
        subject=str(prepared_request.get("subject") or ""),
        instruction_language_code=str(prepared_request.get("instructionLanguageCode") or ""),
        target_language_code=str(prepared_request.get("targetLanguageCode") or ""),
        boundary=boundary,
        checkpoint=reconstructed,
    )
    normalized_input = _normalize_phase_checkpoint(
        command,
        io,
        reconstructed,
        provider=provider_profile,
    )
    request = dict(prepared_request)
    request["phase"] = "independent_verification"
    request["phaseOrdinal"] = 11
    request["checkpoint"] = normalized_input
    canonical = _canonical_dispatch_json(request)
    if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != phase_11_row.get("input_sha256"):
        raise ValueError("phase 11 input hash does not prove phase 14 inventory")


def _normalize_attempt_initial_checkpoint(
    raw: Mapping[str, object],
    *,
    prepared_request: Mapping[str, object],
    build_item_id: str,
    logical_attempt: int,
    generation_request_id: str,
) -> dict[str, object]:
    from integrations.openmaic_question_adapter import (
        QUESTION_PHASE_IO,
        QuestionPhaseCommand,
        _normalize_phase_checkpoint,
    )

    if not isinstance(raw, Mapping) or set(raw) != {
        "questionCount",
        "existingFingerprints",
        "generationFeedback",
    }:
        raise ValueError("provider dispatch attempt-initial checkpoint is invalid")
    boundary = prepared_request.get("skillBoundary")
    provider_profile = prepared_request.get("provider")
    if not isinstance(boundary, Mapping) or not isinstance(
        provider_profile, Mapping
    ):
        raise ValueError("provider dispatch stable request authority is invalid")
    io = QUESTION_PHASE_IO[0]
    command = QuestionPhaseCommand(
        build_item_id=build_item_id,
        logical_attempt=logical_attempt,
        phase="outline",
        phase_ordinal=1,
        generation_request_id=generation_request_id,
        grade_code=str(prepared_request.get("gradeCode") or ""),
        subject=str(prepared_request.get("subject") or ""),
        instruction_language_code=str(
            prepared_request.get("instructionLanguageCode") or ""
        ),
        target_language_code=str(
            prepared_request.get("targetLanguageCode") or ""
        ),
        boundary=boundary,
        checkpoint=raw,
    )
    normalized = _normalize_phase_checkpoint(
        command,
        io,
        raw,
        provider=provider_profile,
    )
    if _canonical_dispatch_json(raw) != _canonical_dispatch_json(normalized):
        raise ValueError("provider dispatch attempt-initial checkpoint is not canonical")
    return normalized


def _reserve_provider_dispatch_strict(
    conn: DatabaseConnection,
    *,
    build_item_id: str,
    logical_attempt: int,
    phase: str,
    phase_ordinal: int,
    generation_request_id: str,
    item_lease_token: str,
    provider: str,
    model: str,
    profile: str,
    input_sha256: str,
    attempt_started_at: int,
    attempt_hard_deadline_at: int,
    work_unit_deadline_at: int,
    lease_expires_at: int,
    attempt_initial_checkpoint: Mapping[str, object],
    command_checkpoint: Mapping[str, object],
    prepared_request: Mapping[str, object],
    required_budget_ms: int,
    clock_ms: Callable[[], int],
) -> ProviderDispatchReservation:
    if type(logical_attempt) is not int or logical_attempt not in (1, 2):
        raise ValueError("provider dispatch logical attempt must be one or two")
    static_phase = provider_phase(phase, phase_ordinal)
    for field, value in (
        ("build item", build_item_id),
        ("item lease", item_lease_token),
    ):
        _validate_dispatch_identifier(value, field)
    _validate_strict_request_id(generation_request_id)
    _validate_dispatch_storage_text(provider, "provider")
    _validate_dispatch_storage_text(model, "model")
    _validate_sha256(profile, "profile")
    _validate_sha256(input_sha256, "input_sha256")
    for field, value in (
        ("attempt_started_at", attempt_started_at),
        ("attempt_hard_deadline_at", attempt_hard_deadline_at),
        ("work_unit_deadline_at", work_unit_deadline_at),
        ("lease_expires_at", lease_expires_at),
        ("required_budget_ms", required_budget_ms),
    ):
        _validate_dispatch_time(value, field)
    if required_budget_ms < 10_000 or not callable(clock_ms):
        raise ValueError("provider dispatch deadline budget is invalid")
    _validate_strict_reservation_request(
        phase=phase,
        phase_ordinal=phase_ordinal,
        generation_request_id=generation_request_id,
        provider=provider,
        model=model,
        profile=profile,
        input_sha256=input_sha256,
        command_checkpoint=command_checkpoint,
        prepared_request=prepared_request,
    )
    normalized_initial = _normalize_attempt_initial_checkpoint(
        attempt_initial_checkpoint,
        prepared_request=prepared_request,
        build_item_id=build_item_id,
        logical_attempt=logical_attempt,
        generation_request_id=generation_request_id,
    )
    current_checkpoint = prepared_request.get("checkpoint")
    if not isinstance(current_checkpoint, Mapping):
        raise ValueError("provider dispatch current checkpoint is invalid")
    if phase_ordinal <= 4:
        carried = {
            key: current_checkpoint.get(key)
            for key in (
                "questionCount",
                "existingFingerprints",
                "generationFeedback",
            )
        }
        if _canonical_dispatch_json(carried) != _canonical_dispatch_json(
            normalized_initial
        ):
            raise ValueError("provider dispatch attempt-initial carry drift")

    item = conn.execute(
        """
        SELECT * FROM learning_catalog_build_items
        WHERE id = ? LIMIT 1 FOR UPDATE
        """,
        (build_item_id,),
    ).fetchone()
    boundary = prepared_request.get("skillBoundary")
    if not isinstance(boundary, Mapping):
        raise ValueError("provider dispatch skill boundary is invalid")
    grade_code = str(prepared_request.get("gradeCode") or "")
    subject = str(prepared_request.get("subject") or "")
    skill_id = str(boundary.get("skillId") or "")
    if not _strict_item_matches(
        item,
        grade_code=grade_code,
        subject=subject,
        skill_id=skill_id,
        logical_attempt=logical_attempt,
        phase=static_phase.phase,
        generation_request_id=generation_request_id,
        item_lease_token=item_lease_token,
        attempt_started_at=attempt_started_at,
        attempt_hard_deadline_at=attempt_hard_deadline_at,
        work_unit_deadline_at=work_unit_deadline_at,
        lease_expires_at=lease_expires_at,
    ):
        raise ValueError("provider dispatch item lease identity mismatch")

    predecessor_rows = conn.execute(
        """
        SELECT * FROM learning_course_provider_dispatches
        WHERE build_item_id = ? AND logical_attempt = ?
          AND phase_ordinal < ?
        ORDER BY phase_ordinal ASC
        FOR UPDATE
        """,
        (build_item_id, logical_attempt, static_phase.phase_ordinal),
    ).fetchall()
    normalized_by_phase = _normalize_locked_predecessors(
        predecessor_rows,
        prepared_request=prepared_request,
        logical_attempt=logical_attempt,
        generation_request_id=generation_request_id,
        provider=provider,
        model=model,
        profile=profile,
        attempt_initial_checkpoint=normalized_initial,
    )
    _verify_current_transition(
        phase=static_phase.phase,
        prepared_request=prepared_request,
        normalized_by_phase=normalized_by_phase,
    )
    if static_phase.phase == "verification_after_repair":
        _verify_phase_14_inventory_proof(
            prepared_request=prepared_request,
            normalized_by_phase=normalized_by_phase,
            predecessor_rows=predecessor_rows,
        )

    dispatch_id = _dispatch_id_for(
        build_item_id, logical_attempt, static_phase.phase, static_phase.phase_ordinal
    )
    existing = conn.execute(
        """
        SELECT * FROM learning_course_provider_dispatches
        WHERE build_item_id = ? AND logical_attempt = ?
          AND (phase = ? OR phase_ordinal = ?)
        LIMIT 1 FOR UPDATE
        """,
        (
            build_item_id,
            logical_attempt,
            static_phase.phase,
            static_phase.phase_ordinal,
        ),
    ).fetchone()
    immutable = {
        "id": dispatch_id,
        "build_item_id": build_item_id,
        "logical_attempt": logical_attempt,
        "phase": static_phase.phase,
        "phase_ordinal": static_phase.phase_ordinal,
        "generation_request_id": generation_request_id,
        "item_lease_token": item_lease_token,
        "provider": provider,
        "model": model,
        "profile": profile,
        "input_sha256": input_sha256,
        "attempt_started_at": attempt_started_at,
        "attempt_hard_deadline_at": attempt_hard_deadline_at,
    }
    if existing is not None:
        if any(str(existing.get(key)) != str(value) for key, value in immutable.items()):
            raise ValueError("provider dispatch replay identity conflict")
        return ProviderDispatchReservation(dispatch=existing, created=False)

    fresh_now = clock_ms()
    if type(fresh_now) is not int or fresh_now < 0:
        raise ValueError("provider dispatch trusted clock is invalid")
    live_item = conn.execute(
        """
        SELECT * FROM learning_catalog_build_items
        WHERE id = ? LIMIT 1 FOR UPDATE
        """,
        (build_item_id,),
    ).fetchone()
    if not _strict_item_matches(
        live_item,
        grade_code=grade_code,
        subject=subject,
        skill_id=skill_id,
        logical_attempt=logical_attempt,
        phase=static_phase.phase,
        generation_request_id=generation_request_id,
        item_lease_token=item_lease_token,
        attempt_started_at=attempt_started_at,
        attempt_hard_deadline_at=attempt_hard_deadline_at,
        work_unit_deadline_at=work_unit_deadline_at,
        lease_expires_at=lease_expires_at,
    ):
        raise ValueError("provider dispatch item deadline identity drift")
    if fresh_now < attempt_started_at or min(
        attempt_hard_deadline_at,
        work_unit_deadline_at,
        lease_expires_at,
    ) - fresh_now < required_budget_ms:
        raise ValueError("provider dispatch deadline budget is insufficient")
    conn.execute(
        """
        INSERT INTO learning_course_provider_dispatches(
          id, build_item_id, logical_attempt, phase, phase_ordinal,
          generation_request_id, item_lease_token, provider, model,
          profile, input_sha256, status, attempt_started_at,
          attempt_hard_deadline_at, dispatched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'dispatched', ?, ?, ?)
        """,
        (
            dispatch_id,
            build_item_id,
            logical_attempt,
            static_phase.phase,
            static_phase.phase_ordinal,
            generation_request_id,
            item_lease_token,
            provider,
            model,
            profile,
            input_sha256,
            attempt_started_at,
            attempt_hard_deadline_at,
            fresh_now,
        ),
    )
    inserted = conn.execute(
        "SELECT * FROM learning_course_provider_dispatches WHERE id = ?",
        (dispatch_id,),
    ).fetchone()
    if inserted is None or any(
        str(inserted.get(key)) != str(value) for key, value in immutable.items()
    ):
        raise ValueError("provider dispatch insert identity conflict")
    return ProviderDispatchReservation(dispatch=inserted, created=True)


def begin_provider_dispatch(
    conn: DatabaseConnection,
    *,
    build_item_id: str,
    logical_attempt: int,
    phase: str,
    phase_ordinal: int,
    generation_request_id: str,
    item_lease_token: str,
    provider: str,
    model: str,
    profile: str,
    input_sha256: str,
    attempt_started_at: int,
    attempt_hard_deadline_at: int,
    dispatched_at: int,
) -> Mapping[str, object]:
    if type(logical_attempt) is not int or logical_attempt not in (1, 2):
        raise ValueError("provider dispatch logical attempt must be one or two")
    static_phase = provider_phase(phase, phase_ordinal)
    for field, value in (
        ("build item", build_item_id),
        ("generation request", generation_request_id),
        ("item lease", item_lease_token),
        ("provider", provider),
        ("model", model),
        ("profile", profile),
    ):
        _validate_dispatch_identifier(value, field)
    _validate_sha256(input_sha256, "input_sha256")
    _validate_dispatch_time(attempt_started_at, "attempt_started_at")
    _validate_dispatch_time(
        attempt_hard_deadline_at, "attempt_hard_deadline_at"
    )
    _validate_dispatch_time(dispatched_at, "dispatched_at")
    if not (
        attempt_started_at <= dispatched_at <= attempt_hard_deadline_at
    ):
        raise ValueError("provider dispatch deadline evidence mismatch")

    item = conn.execute(
        """
        SELECT * FROM learning_catalog_build_items
        WHERE id = ? LIMIT 1 FOR UPDATE
        """,
        (build_item_id,),
    ).fetchone()
    if not (
        item is not None
        and str(item.get("execution_mode_snapshot") or "") == "content_only"
        and str(item.get("status") or "") == "processing"
        and int(item.get("attempt_count") or 0) == logical_attempt
        and int(item.get("content_claim_attempt_ordinal") or 0)
        == logical_attempt
        and str(item.get("content_phase") or "") == static_phase.phase
        and str(item.get("active_generation_request_id") or "")
        == generation_request_id
        and str(item.get("content_lease_token") or "") == item_lease_token
        and item.get("content_attempt_started_at") is not None
        and int(item["content_attempt_started_at"]) == attempt_started_at
        and item.get("content_provider_attempt_hard_deadline_at") is not None
        and int(item["content_provider_attempt_hard_deadline_at"])
        == attempt_hard_deadline_at
        and item.get("content_work_unit_deadline_at") is not None
        and int(dispatched_at) <= int(item["content_work_unit_deadline_at"])
        and item.get("content_lease_expires_at") is not None
        and int(dispatched_at) <= int(item["content_lease_expires_at"])
    ):
        raise ValueError("provider dispatch item lease identity mismatch")

    identity = (
        f"{build_item_id}:{logical_attempt}:"
        f"{static_phase.phase}:{static_phase.phase_ordinal}"
    )
    dispatch_id = (
        "learning_provider_dispatch_"
        + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:48]
    )
    existing = conn.execute(
        """
        SELECT * FROM learning_course_provider_dispatches
        WHERE build_item_id = ? AND logical_attempt = ?
          AND (phase = ? OR phase_ordinal = ?)
        LIMIT 1 FOR UPDATE
        """,
        (
            build_item_id,
            logical_attempt,
            static_phase.phase,
            static_phase.phase_ordinal,
        ),
    ).fetchone()
    if existing is None:
        blocker = conn.execute(
            """
            SELECT status FROM learning_course_provider_dispatches
            WHERE build_item_id = ?
              AND status IN ('dispatched', 'failed_safe', 'ambiguous')
            ORDER BY CASE WHEN status = 'dispatched' THEN 1 ELSE 0 END,
              logical_attempt, phase_ordinal
            LIMIT 1 FOR UPDATE
            """,
            (build_item_id,),
        ).fetchone()
        if blocker is not None:
            if str(blocker["status"]) == "dispatched":
                raise ValueError(
                    "unfinished provider dispatch blocks a new phase"
                )
            raise ValueError(
                "terminal provider dispatch blocks external replay"
            )
        succeeded = conn.execute(
            """
            SELECT phase_ordinal
            FROM learning_course_provider_dispatches
            WHERE build_item_id = ? AND logical_attempt = ?
              AND status = 'succeeded'
            ORDER BY phase_ordinal DESC
            LIMIT 1 FOR UPDATE
            """,
            (build_item_id, logical_attempt),
        ).fetchone()
        if succeeded is None:
            if static_phase.phase_ordinal != 1:
                raise ValueError(
                    "first provider dispatch phase ordinal must be one"
                )
        elif static_phase.phase_ordinal <= int(succeeded["phase_ordinal"]):
            raise ValueError(
                "provider dispatch phase ordinal must advance beyond "
                "the succeeded checkpoint"
            )
        conn.execute(
            """
            INSERT INTO learning_course_provider_dispatches(
              id, build_item_id, logical_attempt, phase, phase_ordinal,
              generation_request_id, item_lease_token, provider, model,
              profile, input_sha256, status, attempt_started_at,
              attempt_hard_deadline_at, dispatched_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'dispatched', ?, ?, ?)
            """,
            (
                dispatch_id,
                build_item_id,
                logical_attempt,
                static_phase.phase,
                static_phase.phase_ordinal,
                generation_request_id,
                item_lease_token,
                provider,
                model,
                profile,
                input_sha256,
                attempt_started_at,
                attempt_hard_deadline_at,
                dispatched_at,
            ),
        )
        existing = conn.execute(
            "SELECT * FROM learning_course_provider_dispatches WHERE id = ?",
            (dispatch_id,),
        ).fetchone()

    immutable = {
        "id": dispatch_id,
        "build_item_id": build_item_id,
        "logical_attempt": logical_attempt,
        "phase": static_phase.phase,
        "phase_ordinal": static_phase.phase_ordinal,
        "generation_request_id": generation_request_id,
        "item_lease_token": item_lease_token,
        "provider": provider,
        "model": model,
        "profile": profile,
        "input_sha256": input_sha256,
        "attempt_started_at": attempt_started_at,
        "attempt_hard_deadline_at": attempt_hard_deadline_at,
        "dispatched_at": dispatched_at,
    }
    if existing is None or any(
        str(existing[key]) != str(value) for key, value in immutable.items()
    ):
        raise ValueError("provider dispatch identity conflict")
    return existing


def _validate_strict_terminal_result(
    *,
    outcome: object,
    checkpoint: object,
    output_sha256: object,
    provider_request_id_hash: object,
    input_tokens: object,
    output_tokens: object,
    billing_evidence: object,
    safe_error_code: object,
) -> None:
    if outcome not in {"succeeded", "failed_safe", "ambiguous"}:
        raise ValueError("unsupported provider dispatch outcome")
    for field, value in (
        ("input_tokens", input_tokens),
        ("output_tokens", output_tokens),
    ):
        if value is not None and (
            type(value) is not int or not 0 <= value <= 2_147_483_647
        ):
            raise ValueError(f"{field} must fit a signed MySQL INTEGER")
    expected_billing = (
        "reported"
        if input_tokens is not None or output_tokens is not None
        else "unknown"
    )
    if billing_evidence != expected_billing:
        raise ValueError("provider billing evidence is not derived from usage")
    if provider_request_id_hash is not None:
        _validate_sha256(
            provider_request_id_hash, "provider_request_id_hash"
        )

    if outcome == "succeeded":
        if not isinstance(checkpoint, Mapping):
            raise ValueError("succeeded dispatch requires a normalized checkpoint")
        if not isinstance(output_sha256, str):
            raise ValueError("succeeded dispatch requires an output hash")
        _validate_sha256(output_sha256, "output_sha256")
        if safe_error_code is not None:
            raise ValueError("succeeded dispatch cannot contain a safe error")
        checkpoint_json = _canonical_dispatch_json(checkpoint)
        expected_output = hashlib.sha256(
            checkpoint_json.encode("utf-8")
        ).hexdigest()
        if output_sha256 != expected_output:
            raise ValueError("provider dispatch output hash mismatch")
        return

    if checkpoint is not None or output_sha256 is not None:
        raise ValueError("failed dispatch cannot contain candidate evidence")
    if not isinstance(safe_error_code, str) or not _SAFE_DISPATCH_CODE.fullmatch(
        safe_error_code
    ):
        raise ValueError("failed dispatch requires a stable safe error code")
    allowed_codes = (
        _FAILED_SAFE_DISPATCH_CODES
        if outcome == "failed_safe"
        else _AMBIGUOUS_DISPATCH_CODES
    )
    if safe_error_code not in allowed_codes:
        raise ValueError("provider dispatch outcome/safe-code pairing is invalid")


def complete_provider_dispatch(
    conn: DatabaseConnection,
    *,
    dispatch_id: str,
    build_item_id: str,
    generation_request_id: str,
    item_lease_token: str,
    outcome: str,
    checkpoint: Mapping[str, object] | None,
    output_sha256: str | None,
    provider_request_id_hash: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    billing_evidence: str,
    safe_error_code: str | None,
    completed_at: int,
) -> bool:
    _validate_strict_terminal_result(
        outcome=outcome,
        checkpoint=checkpoint,
        output_sha256=output_sha256,
        provider_request_id_hash=provider_request_id_hash,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        billing_evidence=billing_evidence,
        safe_error_code=safe_error_code,
    )
    for field, value in (
        ("dispatch", dispatch_id),
        ("build item", build_item_id),
        ("generation request", generation_request_id),
        ("item lease", item_lease_token),
    ):
        _validate_dispatch_identifier(value, field)
    if outcome not in {"succeeded", "failed_safe", "ambiguous"}:
        raise ValueError("unsupported provider dispatch outcome")
    if billing_evidence not in {"reported", "unknown"}:
        raise ValueError("provider billing evidence must be reported or unknown")
    _validate_dispatch_time(completed_at, "completed_at")
    for field, value in (
        ("input_tokens", input_tokens),
        ("output_tokens", output_tokens),
    ):
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(f"{field} must be a non-negative integer")
    if provider_request_id_hash is not None:
        _validate_sha256(
            provider_request_id_hash, "provider_request_id_hash"
        )

    if outcome == "succeeded":
        if not isinstance(checkpoint, Mapping):
            raise ValueError("succeeded dispatch requires a normalized checkpoint")
        if output_sha256 is None:
            raise ValueError("succeeded dispatch requires an output hash")
        _validate_sha256(output_sha256, "output_sha256")
        if safe_error_code is not None:
            raise ValueError("succeeded dispatch cannot contain a safe error")
        checkpoint_json = json.dumps(
            dict(checkpoint),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    else:
        if checkpoint is not None or output_sha256 is not None:
            raise ValueError("failed dispatch cannot contain candidate evidence")
        if not isinstance(safe_error_code, str) or not _SAFE_DISPATCH_CODE.fullmatch(
            safe_error_code
        ):
            raise ValueError("failed dispatch requires a stable safe error code")
        checkpoint_json = None

    item = conn.execute(
        """
        SELECT * FROM learning_catalog_build_items
        WHERE id = ?
        LIMIT 1 FOR UPDATE
        """,
        (build_item_id,),
    ).fetchone()
    if not (
        item is not None
        and str(item.get("execution_mode_snapshot") or "") == "content_only"
        and str(item.get("status") or "") == "processing"
        and str(item.get("active_generation_request_id") or "")
        == generation_request_id
        and str(item.get("content_lease_token") or "") == item_lease_token
        and item.get("content_lease_expires_at") is not None
        and int(item["content_lease_expires_at"]) >= completed_at
        and item.get("content_work_unit_deadline_at") is not None
        and int(item["content_work_unit_deadline_at"]) >= completed_at
        and item.get("content_provider_attempt_hard_deadline_at") is not None
        and int(item["content_provider_attempt_hard_deadline_at"])
        >= completed_at
    ):
        return False
    row = conn.execute(
        """
        SELECT * FROM learning_course_provider_dispatches
        WHERE id = ? AND build_item_id = ?
          AND generation_request_id = ?
          AND item_lease_token = ?
          AND status = 'dispatched'
        LIMIT 1 FOR UPDATE
        """,
        (
            dispatch_id,
            build_item_id,
            generation_request_id,
            item_lease_token,
        ),
    ).fetchone()
    if not (
        row is not None
        and int(item.get("attempt_count") or 0)
        == int(row.get("logical_attempt") or 0)
        and int(item.get("content_claim_attempt_ordinal") or 0)
        == int(row.get("logical_attempt") or 0)
        and str(item.get("content_phase") or "") == str(row.get("phase") or "")
        and item.get("content_attempt_started_at") is not None
        and int(item["content_attempt_started_at"])
        == int(row.get("attempt_started_at") or -1)
        and int(item["content_provider_attempt_hard_deadline_at"])
        == int(row.get("attempt_hard_deadline_at") or -1)
    ):
        return False
    cursor = conn.execute(
        """
        UPDATE learning_course_provider_dispatches
        SET status = ?, checkpoint_json = ?, output_sha256 = ?,
          provider_request_id_hash = ?, input_tokens = ?, output_tokens = ?,
          billing_evidence = ?, safe_error_code = ?, completed_at = ?
        WHERE id = ? AND build_item_id = ? AND status = 'dispatched'
          AND generation_request_id = ? AND item_lease_token = ?
        """,
        (
            outcome,
            checkpoint_json,
            output_sha256,
            provider_request_id_hash,
            input_tokens,
            output_tokens,
            billing_evidence,
            safe_error_code,
            completed_at,
            dispatch_id,
            build_item_id,
            generation_request_id,
            item_lease_token,
        ),
    )
    return cursor.rowcount == 1


def _validate_dispatch_identifier(value: object, field: str) -> None:
    if not isinstance(value, str) or not _DISPATCH_IDENTIFIER.fullmatch(value):
        raise ValueError(f"provider dispatch {field} identity is invalid")


def _validate_strict_request_id(value: object) -> None:
    if not isinstance(value, str) or re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}", value
    ) is None:
        raise ValueError("provider dispatch generation request identity is invalid")


def _validate_dispatch_storage_text(value: object, field: str) -> None:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError(f"provider dispatch {field} text is invalid")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ValueError(f"provider dispatch {field} text is invalid") from exc


def _validate_sha256(value: object, field: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256")


def _validate_dispatch_time(value: object, field: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")


class LearningCourseGenerationRequestConflict(ValueError):
    """A request id was replayed with a different generation specification."""


class LearningCourseCandidateConflict(ValueError):
    """A candidate ordinal or course identity was reused with different content."""


class LearningCoursePublicationConflict(ValueError):
    """The generated course identity is already owned by different content."""


class DynamicLearningCourseRepository:
    """Persistence contract for AI-generated catalog candidates.

    Validation stages a course for lesson-package compilation. It is not
    student-publishable until a catalog release is activated. Historical method
    names are retained where callers rely on them, but ``publish_candidate`` now
    means publishing into the internal candidate registry, not to students.
    """

    DYNAMIC_CONTENT_ORIGIN = "openmaic_generated"

    def __init__(self, database: Database):
        self.database = database

    @contextmanager
    def transaction(self) -> Iterator[DatabaseConnection]:
        with self.database.transaction() as conn:
            yield conn

    def reserve_provider_dispatch(
        self,
        conn: DatabaseConnection,
        **kwargs: Any,
    ) -> ProviderDispatchReservation:
        return _reserve_provider_dispatch_strict(conn, **kwargs)

    def complete_provider_dispatch(
        self,
        conn: DatabaseConnection,
        **kwargs: Any,
    ) -> bool:
        _validate_strict_terminal_result(
            outcome=kwargs.get("outcome"),
            checkpoint=kwargs.get("checkpoint"),
            output_sha256=kwargs.get("output_sha256"),
            provider_request_id_hash=kwargs.get("provider_request_id_hash"),
            input_tokens=kwargs.get("input_tokens"),
            output_tokens=kwargs.get("output_tokens"),
            billing_evidence=kwargs.get("billing_evidence"),
            safe_error_code=kwargs.get("safe_error_code"),
        )
        return complete_provider_dispatch(conn, **kwargs)

    def create_or_get_job(
        self,
        conn: DatabaseConnection,
        *,
        request_id: str,
        grade_code: str,
        subject: str,
        node_code: str,
        generator: str,
        provider: str,
        model: str,
        prompt_version: str,
        requested_candidate_count: int,
        generation_spec: Mapping[str, Any] | None,
        now: int,
        curriculum_version: str = "legacy",
        boundary_version: str = "legacy",
    ) -> tuple[DatabaseRow, bool]:
        fingerprint = self.request_fingerprint(
            grade_code=grade_code,
            subject=subject,
            node_code=node_code,
            curriculum_version=curriculum_version,
            boundary_version=boundary_version,
            generator=generator,
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            requested_candidate_count=requested_candidate_count,
            generation_spec=generation_spec,
        )
        job_id = f"learning_course_job_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO learning_course_generation_jobs(
              id, request_id, request_fingerprint, grade_code, subject,
              node_code, curriculum_version, boundary_version,
              generator, provider, model, prompt_version,
              requested_candidate_count, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?)
            ON DUPLICATE KEY UPDATE id = id
            """,
            (
                job_id,
                request_id,
                fingerprint,
                grade_code,
                subject,
                node_code,
                curriculum_version,
                boundary_version,
                generator,
                provider,
                model,
                prompt_version,
                max(1, int(requested_candidate_count)),
                now,
                now,
            ),
        )
        job = self.get_job_by_request(conn, request_id=request_id)
        if job is None:
            raise RuntimeError("learning course generation job was not persisted")
        if str(job["request_fingerprint"]) != fingerprint:
            raise LearningCourseGenerationRequestConflict(
                "request_id is already bound to another generation specification"
            )
        return job, str(job["id"]) == job_id

    def get_job_by_request(
        self,
        conn: DatabaseConnection,
        *,
        request_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM learning_course_generation_jobs
            WHERE request_id = ?
            LIMIT 1
            """,
            (request_id,),
        ).fetchone()

    def get_job(
        self,
        conn: DatabaseConnection,
        *,
        job_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock_sql = " FOR UPDATE" if for_update else ""
        return conn.execute(
            f"""
            SELECT * FROM learning_course_generation_jobs
            WHERE id = ?
            LIMIT 1{lock_sql}
            """,
            (job_id,),
        ).fetchone()

    def mark_job_generating(
        self,
        conn: DatabaseConnection,
        *,
        job_id: str,
        now: int,
    ) -> DatabaseRow | None:
        conn.execute(
            """
            UPDATE learning_course_generation_jobs
            SET status = 'generating', started_at = COALESCE(started_at, ?),
              error_code = NULL, error_message_safe = NULL, updated_at = ?
            WHERE id = ? AND status = 'queued'
            """,
            (now, now, job_id),
        )
        return self.get_job(conn, job_id=job_id)

    def reclaim_stale_generating_job(
        self,
        conn: DatabaseConnection,
        *,
        job_id: str,
        stale_before: int,
        now: int,
    ) -> DatabaseRow | None:
        """Reclaim the same logical request after its worker lease expires."""

        cursor = conn.execute(
            """
            UPDATE learning_course_generation_jobs
            SET error_code = NULL, error_message_safe = NULL, updated_at = ?
            WHERE id = ? AND status = 'generating' AND updated_at < ?
            """,
            (now, job_id, stale_before),
        )
        if cursor.rowcount != 1:
            return None
        return self.get_job(conn, job_id=job_id)

    def reclaim_retryable_failed_job(
        self,
        conn: DatabaseConnection,
        *,
        job_id: str,
        expected_error_code: str,
        expected_updated_at: int,
        now: int,
    ) -> DatabaseRow | None:
        """Replay the same failed provider request after explicit operator approval."""

        cursor = conn.execute(
            """
            UPDATE learning_course_generation_jobs
            SET status = 'generating', error_code = NULL,
              error_message_safe = NULL, completed_at = NULL, updated_at = ?
            WHERE id = ? AND status = 'failed' AND error_code = ?
              AND updated_at = ?
            """,
            (now, job_id, expected_error_code, int(expected_updated_at)),
        )
        if cursor.rowcount != 1:
            return None
        return self.get_job(conn, job_id=job_id)

    def create_or_get_candidate(
        self,
        conn: DatabaseConnection,
        *,
        job_id: str,
        ordinal: int,
        course: Mapping[str, Any],
        now: int,
    ) -> tuple[DatabaseRow, bool]:
        if int(ordinal) < 1:
            raise ValueError("candidate ordinal must be positive")
        job = self.get_job(conn, job_id=job_id)
        if job is None:
            raise ValueError("learning course generation job was not found")

        normalized = self._normalize_course(course)
        self._assert_candidate_target(job, normalized)
        content_json = self.encode_json(normalized["content"])
        content_hash = self.candidate_fingerprint(normalized)
        candidate_id = f"learning_course_candidate_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO learning_course_generation_candidates(
              id, job_id, ordinal, course_id, course_version, grade_code,
              subject, node_code, curriculum_version, boundary_version,
              title, objective, status, content_hash,
              content_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'generated', ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE id = id
            """,
            (
                candidate_id,
                job_id,
                int(ordinal),
                normalized["id"],
                normalized["version"],
                normalized["gradeCode"],
                normalized["subject"],
                normalized["nodeCode"],
                job["curriculum_version"],
                job["boundary_version"],
                normalized["title"],
                normalized["objective"],
                content_hash,
                content_json,
                now,
                now,
            ),
        )
        candidate = self.get_candidate_for_ordinal(
            conn,
            job_id=job_id,
            ordinal=int(ordinal),
        )
        if candidate is None:
            raise RuntimeError("learning course candidate was not persisted")
        if (
            str(candidate["course_id"]) != normalized["id"]
            or str(candidate["course_version"]) != normalized["version"]
            or str(candidate["content_hash"]) != content_hash
        ):
            raise LearningCourseCandidateConflict(
                "candidate ordinal is already bound to different content"
            )
        return candidate, str(candidate["id"]) == candidate_id

    def get_candidate_for_ordinal(
        self,
        conn: DatabaseConnection,
        *,
        job_id: str,
        ordinal: int,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM learning_course_generation_candidates
            WHERE job_id = ? AND ordinal = ?
            LIMIT 1
            """,
            (job_id, int(ordinal)),
        ).fetchone()

    def get_candidate(
        self,
        conn: DatabaseConnection,
        *,
        candidate_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock_sql = " FOR UPDATE" if for_update else ""
        return conn.execute(
            f"""
            SELECT * FROM learning_course_generation_candidates
            WHERE id = ?
            LIMIT 1{lock_sql}
            """,
            (candidate_id,),
        ).fetchone()

    def list_candidates(
        self,
        conn: DatabaseConnection,
        *,
        job_id: str,
    ) -> list[DatabaseRow]:
        return list(
            conn.execute(
                """
                SELECT * FROM learning_course_generation_candidates
                WHERE job_id = ?
                ORDER BY ordinal, id
                """,
                (job_id,),
            ).fetchall()
        )

    def mark_candidate_validated(
        self,
        conn: DatabaseConnection,
        *,
        candidate_id: str,
        validation: Mapping[str, Any],
        now: int,
    ) -> DatabaseRow | None:
        semantic_fingerprint = str(
            validation.get("contentFingerprint") or ""
        ).strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", semantic_fingerprint):
            raise ValueError("validated candidate requires a semantic content fingerprint")
        candidate = self.get_candidate(conn, candidate_id=candidate_id)
        if candidate is None:
            return None
        conn.execute(
            """
            UPDATE learning_course_generation_candidates
            SET status = 'validated', validation_json = ?, error_code = NULL,
              error_message_safe = NULL, updated_at = ?
            WHERE id = ? AND status IN ('generated', 'validated')
            """,
            (self.encode_json(validation), now, candidate_id),
        )
        conn.execute(
            """
            UPDATE learning_course_generation_jobs
            SET status = 'candidates_ready', updated_at = ?
            WHERE id = ? AND status IN ('queued', 'generating', 'candidates_ready')
            """,
            (now, candidate["job_id"]),
        )
        return self.get_candidate(conn, candidate_id=candidate_id)

    def reject_candidate(
        self,
        conn: DatabaseConnection,
        *,
        candidate_id: str,
        error_code: str,
        error_message: str,
        validation: Mapping[str, Any] | None,
        now: int,
    ) -> DatabaseRow | None:
        conn.execute(
            """
            UPDATE learning_course_generation_candidates
            SET status = 'rejected', validation_json = ?, error_code = ?,
              error_message_safe = ?, updated_at = ?
            WHERE id = ? AND status IN ('generated', 'validated', 'rejected')
            """,
            (
                self.encode_json(validation) if validation is not None else None,
                self._safe_code(error_code),
                self.sanitize_error(error_message),
                now,
                candidate_id,
            ),
        )
        return self.get_candidate(conn, candidate_id=candidate_id)

    def mark_job_failed(
        self,
        conn: DatabaseConnection,
        *,
        job_id: str,
        error_code: str,
        error_message: str,
        now: int,
    ) -> DatabaseRow | None:
        conn.execute(
            """
            UPDATE learning_course_generation_jobs
            SET status = 'failed', error_code = ?, error_message_safe = ?,
              completed_at = ?, updated_at = ?
            WHERE id = ? AND status NOT IN ('partially_validated', 'validated')
            """,
            (
                self._safe_code(error_code),
                self.sanitize_error(error_message),
                now,
                now,
                job_id,
            ),
        )
        return self.get_job(conn, job_id=job_id)

    def stage_candidate(
        self,
        *,
        candidate_id: str,
        now: int,
    ) -> tuple[DatabaseRow, bool]:
        """Atomically stage one validated candidate for package compilation."""

        with self.transaction() as conn:
            candidate = self.get_candidate(
                conn,
                candidate_id=candidate_id,
                for_update=True,
            )
            if candidate is None:
                raise ValueError("learning course candidate was not found")
            job = self.get_job(
                conn,
                job_id=str(candidate["job_id"]),
                for_update=True,
            )
            if job is None:
                raise ValueError("learning course generation job was not found")
            if str(job["status"]) == "failed":
                raise LearningCoursePublicationConflict(
                    "a failed generation job cannot publish candidates"
                )
            if str(candidate["status"]) not in {"validated", "course_validated"}:
                raise LearningCoursePublicationConflict(
                    "only a validated candidate can be published"
                )

            was_published = str(candidate["status"]) == "course_validated"
            semantic_fingerprint = self._publication_fingerprint(candidate)
            conn.execute(
                """
                INSERT INTO learning_courses(
                  id, version, grade_code, subject, node_code,
                  curriculum_version, boundary_version, title,
                  objective, status, quality_status, content_origin, generator,
                  generation_request_id, generation_content_hash,
                  content_json, published_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'validated',
                  'auto_validated', ?, ?, ?, ?, ?, NULL, ?, ?)
                ON DUPLICATE KEY UPDATE id = id
                """,
                (
                    candidate["course_id"],
                    candidate["course_version"],
                    candidate["grade_code"],
                    candidate["subject"],
                    candidate["node_code"],
                    candidate["curriculum_version"],
                    candidate["boundary_version"],
                    candidate["title"],
                    candidate["objective"],
                    self.DYNAMIC_CONTENT_ORIGIN,
                    job["generator"],
                    job["request_id"],
                    semantic_fingerprint,
                    candidate["content_json"],
                    now,
                    now,
                ),
            )
            course = conn.execute(
                """
                SELECT * FROM learning_courses
                WHERE id = ? AND version = ?
                LIMIT 1 FOR UPDATE
                """,
                (candidate["course_id"], candidate["course_version"]),
            ).fetchone()
            if not self._course_is_same_publication(
                course,
                candidate=candidate,
                job=job,
                publication_fingerprint=semantic_fingerprint,
            ):
                raise LearningCoursePublicationConflict(
                    "course id and version are already owned by different content"
                )

            conn.execute(
                """
                UPDATE learning_course_generation_candidates
                SET status = 'course_validated', published_at = NULL,
                  updated_at = ?
                WHERE id = ?
                """,
                (now, candidate_id),
            )
            counts = conn.execute(
                """
                SELECT COUNT(*) AS total,
                  SUM(CASE WHEN status = 'course_validated' THEN 1 ELSE 0 END) AS published
                FROM learning_course_generation_candidates
                WHERE job_id = ?
                """,
                (job["id"],),
            ).fetchone()
            published_count = int((counts or {}).get("published") or 0)
            expected_count = max(1, int(job["requested_candidate_count"] or 1))
            job_status = (
                "validated"
                if published_count >= expected_count
                else "partially_validated"
            )
            completed_at = now if job_status == "validated" else None
            conn.execute(
                """
                UPDATE learning_course_generation_jobs
                SET status = ?,
                  completed_at = CASE
                    WHEN ? = 'validated' THEN COALESCE(completed_at, ?)
                    ELSE NULL
                  END,
                  error_code = NULL,
                  error_message_safe = NULL, updated_at = ?
                WHERE id = ?
                """,
                (job_status, job_status, completed_at, now, job["id"]),
            )
            return course, not was_published

    def publish_candidate(
        self,
        *,
        candidate_id: str,
        now: int,
    ) -> tuple[DatabaseRow, bool]:
        """Backward-compatible alias for the pre-release staging operation."""

        return self.stage_candidate(candidate_id=candidate_id, now=now)

    def list_published_dynamic_courses(
        self,
        conn: DatabaseConnection,
        *,
        grade_code: str,
        subject: str | None = None,
        node_code: str | None = None,
        curriculum_version: str | None = None,
        boundary_version: str | None = None,
    ) -> list[DatabaseRow]:
        clauses = [
            "grade_code = ?",
            "status IN ('validated', 'published')",
            "retired_at IS NULL",
            "content_origin = ?",
        ]
        params: list[object] = [grade_code, self.DYNAMIC_CONTENT_ORIGIN]
        if subject:
            clauses.append("subject = ?")
            params.append(subject)
        if node_code:
            clauses.append("node_code = ?")
            params.append(node_code)
        if curriculum_version:
            clauses.append("curriculum_version = ?")
            params.append(curriculum_version)
        if boundary_version:
            clauses.append("boundary_version = ?")
            params.append(boundary_version)
        return list(
            conn.execute(
                f"""
                SELECT * FROM learning_courses
                WHERE {' AND '.join(clauses)}
                ORDER BY published_at, id, version
                """,
                params,
            ).fetchall()
        )

    def count_published_dynamic_courses(
        self,
        conn: DatabaseConnection,
        *,
        grade_code: str,
        subject: str | None = None,
        node_code: str | None = None,
        curriculum_version: str | None = None,
        boundary_version: str | None = None,
    ) -> int:
        clauses = [
            "grade_code = ?",
            "status IN ('validated', 'published')",
            "retired_at IS NULL",
            "content_origin = ?",
        ]
        params: list[object] = [grade_code, self.DYNAMIC_CONTENT_ORIGIN]
        if subject:
            clauses.append("subject = ?")
            params.append(subject)
        if node_code:
            clauses.append("node_code = ?")
            params.append(node_code)
        if curriculum_version:
            clauses.append("curriculum_version = ?")
            params.append(curriculum_version)
        if boundary_version:
            clauses.append("boundary_version = ?")
            params.append(boundary_version)
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS value FROM learning_courses
            WHERE {' AND '.join(clauses)}
            """,
            params,
        ).fetchone()
        return int((row or {}).get("value") or 0)

    def existing_content_fingerprints(
        self,
        conn: DatabaseConnection,
        *,
        grade_code: str,
        subject: str,
        node_code: str | None = None,
    ) -> set[str]:
        node_clause = " AND node_code = ?" if node_code else ""
        candidate_params: list[object] = [grade_code, subject]
        course_params: list[object] = [grade_code, subject]
        if node_code:
            candidate_params.append(node_code)
            course_params.append(node_code)
        rows = conn.execute(
            f"""
            SELECT content_hash, validation_json
            FROM learning_course_generation_candidates
            WHERE grade_code = ? AND subject = ?
              AND status IN ('validated', 'course_validated')
              {node_clause}
            """,
            candidate_params,
        ).fetchall()
        fingerprints: set[str] = set()
        for row in rows:
            validation = self._decoded_mapping(row.get("validation_json"))
            semantic = str(
                validation.get("contentFingerprint") or ""
            ).strip().lower()
            if re.fullmatch(r"[0-9a-f]{64}", semantic):
                fingerprints.add(semantic)

        course_rows = conn.execute(
            f"""
            SELECT generation_content_hash AS fingerprint
            FROM learning_courses
            WHERE grade_code = ? AND subject = ?
              AND status IN ('validated', 'published')
              AND generation_content_hash IS NOT NULL
              {node_clause}
            """,
            course_params,
        ).fetchall()
        fingerprints.update(
            str(row["fingerprint"]).strip().lower()
            for row in course_rows
            if re.fullmatch(
                r"[0-9a-f]{64}", str(row.get("fingerprint") or "").strip().lower()
            )
        )
        return fingerprints

    def existing_question_fingerprints(
        self,
        conn: DatabaseConnection,
        *,
        grade_code: str,
        subject: str,
        node_code: str,
    ) -> set[str]:
        """Return fingerprints compatible with the OpenMAIC sidecar contract."""

        rows = conn.execute(
            """
            SELECT content_json
            FROM learning_course_generation_candidates
            WHERE grade_code = ? AND subject = ? AND node_code = ?
              AND status IN ('generated', 'validated', 'course_validated')
            UNION ALL
            SELECT content_json
            FROM learning_courses
            WHERE grade_code = ? AND subject = ? AND node_code = ?
              AND status IN ('validated', 'published')
            """,
            (grade_code, subject, node_code, grade_code, subject, node_code),
        ).fetchall()
        fingerprints: set[str] = set()
        for row in rows:
            try:
                content = json.loads(str(row.get("content_json") or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            questions = content.get("questions") if isinstance(content, dict) else None
            if not isinstance(questions, list):
                continue
            for question in questions:
                if not isinstance(question, Mapping):
                    continue
                fingerprint = self.question_fingerprint(
                    grade_code=grade_code,
                    subject=subject,
                    node_code=node_code,
                    question=question,
                )
                if fingerprint:
                    fingerprints.add(fingerprint)
        return fingerprints

    @classmethod
    def question_fingerprint(
        cls,
        *,
        grade_code: str,
        subject: str,
        node_code: str,
        question: Mapping[str, Any],
    ) -> str:
        choices = question.get("choices")
        labels = []
        if isinstance(choices, list):
            labels = sorted(
                (
                    cls._question_fingerprint_comparable(item.get("label"))
                    for item in choices
                    if isinstance(item, Mapping)
                ),
                key=lambda value: value.encode("utf-8"),
            )
        public_shape = {
            "gradeCode": str(grade_code),
            "subject": str(subject),
            "skillId": str(node_code),
            "type": str(question.get("type") or ""),
            "prompt": cls._question_fingerprint_comparable(question.get("prompt")),
            "choiceLabels": labels,
        }
        encoded = json.dumps(
            public_shape,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @classmethod
    def request_fingerprint(
        cls,
        *,
        grade_code: str,
        subject: str,
        node_code: str,
        curriculum_version: str,
        boundary_version: str,
        generator: str,
        provider: str,
        model: str,
        prompt_version: str,
        requested_candidate_count: int,
        generation_spec: Mapping[str, Any] | None,
    ) -> str:
        return cls._sha256(
            {
                "gradeCode": grade_code,
                "subject": subject,
                "nodeCode": node_code,
                "curriculumVersion": curriculum_version,
                "boundaryVersion": boundary_version,
                "generator": generator,
                "provider": provider,
                "model": model,
                "promptVersion": prompt_version,
                "requestedCandidateCount": max(
                    1, int(requested_candidate_count)
                ),
                "generationSpec": dict(generation_spec or {}),
            }
        )

    @classmethod
    def candidate_fingerprint(cls, course: Mapping[str, Any]) -> str:
        normalized = cls._normalize_course(course)
        return cls._sha256(
            {
                "gradeCode": normalized["gradeCode"],
                "subject": normalized["subject"],
                "nodeCode": normalized["nodeCode"],
                "title": normalized["title"],
                "objective": normalized["objective"],
                "content": normalized["content"],
            }
        )

    @staticmethod
    def sanitize_error(message: object) -> str:
        text = " ".join(str(message or "generation failed").split())
        text = _SECRET_ASSIGNMENT.sub(r"\1=[REDACTED]", text)
        text = _BEARER_TOKEN.sub("Bearer [REDACTED]", text)
        text = _URL_CREDENTIALS.sub(r"\1[REDACTED]@", text)
        text = _PROVIDER_TOKEN.sub("[REDACTED]", text)
        return text[:512] or "generation failed"

    @staticmethod
    def encode_json(payload: Mapping[str, Any]) -> str:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def _sha256(cls, payload: Mapping[str, Any]) -> str:
        return hashlib.sha256(cls.encode_json(payload).encode("utf-8")).hexdigest()

    @classmethod
    def _normalize_course(cls, course: Mapping[str, Any]) -> dict[str, Any]:
        content = course.get("content")
        if not isinstance(content, Mapping):
            raise ValueError("candidate course content must be an object")
        required = (
            "id",
            "version",
            "gradeCode",
            "subject",
            "nodeCode",
            "title",
            "objective",
        )
        normalized: dict[str, Any] = {}
        for key in required:
            value = str(course.get(key) or "").strip()
            if not value:
                raise ValueError(f"candidate course requires {key}")
            normalized[key] = value
        normalized["content"] = dict(content)
        return normalized

    @staticmethod
    def _assert_candidate_target(
        job: Mapping[str, Any],
        course: Mapping[str, Any],
    ) -> None:
        expected = (
            str(job["grade_code"]),
            str(job["subject"]),
            str(job["node_code"]),
        )
        actual = (
            str(course["gradeCode"]),
            str(course["subject"]),
            str(course["nodeCode"]),
        )
        if actual != expected:
            raise LearningCourseCandidateConflict(
                "candidate changed the requested grade, subject, or skill"
            )

    @classmethod
    def _course_is_same_publication(
        cls,
        course: DatabaseRow | None,
        *,
        candidate: Mapping[str, Any],
        job: Mapping[str, Any],
        publication_fingerprint: str,
    ) -> bool:
        if course is None:
            return False
        return (
            str(course.get("content_origin") or "") == cls.DYNAMIC_CONTENT_ORIGIN
            and str(course.get("generator") or "") == str(job["generator"])
            and str(course.get("generation_request_id") or "")
            == str(job["request_id"])
            and str(course.get("generation_content_hash") or "")
            == publication_fingerprint
            and str(course.get("curriculum_version") or "")
            == str(job.get("curriculum_version") or "")
            and str(course.get("boundary_version") or "")
            == str(job.get("boundary_version") or "")
        )

    @classmethod
    def _publication_fingerprint(cls, candidate: Mapping[str, Any]) -> str:
        validation = cls._decoded_mapping(candidate.get("validation_json"))
        semantic = str(
            validation.get("contentFingerprint") or ""
        ).strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", semantic):
            raise LearningCoursePublicationConflict(
                "validated candidate has no semantic content fingerprint"
            )
        return semantic

    @staticmethod
    def _decoded_mapping(value: object) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        try:
            decoded = json.loads(str(value or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return dict(decoded) if isinstance(decoded, Mapping) else {}

    @staticmethod
    def _safe_code(code: object) -> str:
        value = re.sub(r"[^a-z0-9_.-]", "_", str(code or "generation_failed").lower())
        return value[:128] or "generation_failed"

    @staticmethod
    def _question_fingerprint_comparable(value: object) -> str:
        normalized = unicodedata.normalize("NFKC", str(value or ""))
        comparable: list[str] = []
        for character in normalized:
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
    def _normalized_comparable(value: object) -> str:
        normalized = unicodedata.normalize("NFKC", str(value or ""))
        whitespace = re.compile(
            r"[\u0009-\u000D\u0020\u00A0\u1680\u2000-\u200A"
            r"\u2028\u2029\u202F\u205F\u3000\uFEFF]+"
        )
        return whitespace.sub(" ", normalized).strip().lower()
