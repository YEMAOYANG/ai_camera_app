from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Sequence


QUESTION_PHASE_AUTHORITY_SCHEMA_VERSION = "mira.learning.question-phase-graph.v1"
_QUESTION_PHASE_AUTHORITY_PATH = (
    Path(__file__).resolve().parents[1]
    / "openmaic-sidecar"
    / "contracts"
    / "learning_question_phase_contract.v2.json"
)


def _load_question_phase_authority() -> tuple[str, tuple[tuple[str, int], ...]]:
    with _QUESTION_PHASE_AUTHORITY_PATH.open("r", encoding="utf-8") as handle:
        authority = json.load(handle)
    if not isinstance(authority, dict) or set(authority) != {
        "schemaVersion",
        "questionContractVersion",
        "providerPhases",
    }:
        raise ValueError("question phase authority fields mismatch")
    if authority["schemaVersion"] != QUESTION_PHASE_AUTHORITY_SCHEMA_VERSION:
        raise ValueError("question phase authority schema version mismatch")
    version = authority["questionContractVersion"]
    if not isinstance(version, str) or not version:
        raise ValueError("question contract version must be a non-empty string")
    raw_phases = authority["providerPhases"]
    if not isinstance(raw_phases, list):
        raise ValueError("providerPhases must be an array")
    phases: list[tuple[str, int]] = []
    for item in raw_phases:
        if not isinstance(item, dict) or set(item) != {"phase", "phaseOrdinal"}:
            raise ValueError("provider phase authority entry fields mismatch")
        phase = item["phase"]
        ordinal = item["phaseOrdinal"]
        if not isinstance(phase, str) or not phase:
            raise ValueError("provider phase name must be a non-empty string")
        if type(ordinal) is not int:
            raise ValueError("provider phase ordinal must be an integer")
        phases.append((phase, ordinal))
    return version, tuple(phases)


QUESTION_CONTRACT_VERSION, PROVIDER_PHASES = _load_question_phase_authority()


@dataclass(frozen=True)
class ProviderPhase:
    phase: str
    phase_ordinal: int


def validate_provider_phase_graph(
    phases: Sequence[tuple[str, int]],
) -> tuple[tuple[str, int], ...]:
    normalized = tuple(phases)
    if len(normalized) > 14:
        raise ValueError("provider phase graph supports at most 14 phases")

    names: set[str] = set()
    ordinals: set[int] = set()
    for item in normalized:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ValueError("provider phase entries must be (phase, ordinal) pairs")
        phase, ordinal = item
        if not isinstance(phase, str) or not phase:
            raise ValueError("provider phase name must be a non-empty string")
        if type(ordinal) is not int:
            raise ValueError("provider phase ordinal must be an integer")
        if phase in names:
            raise ValueError("duplicate provider phase")
        if ordinal in ordinals:
            raise ValueError("duplicate phase ordinal")
        names.add(phase)
        ordinals.add(ordinal)

    if normalized != PROVIDER_PHASES:
        raise ValueError("provider phase graph does not match question contract v2")
    return normalized


def provider_phase(phase: str, phase_ordinal: int) -> ProviderPhase:
    expected = dict(PROVIDER_PHASES).get(str(phase or ""))
    if expected is None:
        raise ValueError("unsupported provider phase")
    if type(phase_ordinal) is not int:
        raise ValueError("phase ordinal must be an integer")
    if phase_ordinal != expected:
        raise ValueError("phase ordinal mismatch")
    return ProviderPhase(phase=str(phase), phase_ordinal=expected)


validate_provider_phase_graph(PROVIDER_PHASES)
