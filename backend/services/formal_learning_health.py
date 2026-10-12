from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient
from repositories.learning_curriculum_preparation_repository import (
    LearningCurriculumPreparationRepository,
)
from services.learning_curriculum_preparation_contract import (
    PREPARATION_CONTRACT_VERSION,
    TARGET_SCHEMA_V2,
)


FORMAL_HEALTH_SCHEMA = "mira.learning.formal-production-health.v1"
FORMAL_EVENT_BRIDGE_SCHEMA = "mira.openmaic.student-runtime-events.v1"
FORMAL_EVENT_SCHEMA = "mira.openmaic.student-runtime-event.v1"
FORMAL_EVENT_RECEIPT_SCHEMA = (
    "mira.openmaic.student-runtime-event-receipt.v1"
)
RUNTIME_UPSTREAM_VERSION = "1.0.0"
RUNTIME_UPSTREAM_COMMIT = "aa2bfb3c1d406c47100c6744d90e788abdf1f6d5"
# Deployment pins must match openmaic-runtime/upstream.lock.json.
RUNTIME_PATCH_COUNT = 158
RUNTIME_LATEST_PATCH = "0158-mira-self-narrated-activity-start.patch"
RUNTIME_LATEST_PATCH_SHA256 = (
    "c09c4ddc80da67fcc0a9afb6de0a86d19fae50232204fb137a616c5643ed0ac3"
)


def formal_learning_health_attestation(
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Return non-secret, exact production-contract and gate evidence."""

    grade_allowlist = sorted(
        {
            str(value).strip()
            for value in config.get(
                "LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST", []
            )
            if str(value).strip()
        }
    )
    gates = {
        "contentGeneration": bool(
            config.get("LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED", False)
            and config.get(
                "LEARNING_CURRICULUM_PREPARATION_CONTENT_GENERATION_ENABLED",
                False,
            )
        ),
        "classroomGeneration": bool(
            config.get("LEARNING_CLASSROOM_GENERATION_ENABLED", False)
            and config.get("LEARNING_FORMAL_RUNTIME_CANDIDATE_ENABLED", False)
        ),
        "audioValidation": bool(
            config.get("LEARNING_FORMAL_AUDIO_VALIDATION_ENABLED", False)
        ),
        "automaticPublication": bool(
            config.get("LEARNING_FORMAL_AUTO_PUBLICATION_ENABLED", False)
        ),
        "studentRelease": bool(
            config.get("LEARNING_CLASSROOM_STUDENT_RELEASE_ENABLED", False)
        ),
    }
    classroom_contract = OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CLASSROOM_CONTRACT
    classroom_contract_sha256 = hashlib.sha256(
        json.dumps(
            classroom_contract,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schemaVersion": FORMAL_HEALTH_SCHEMA,
        "gradeAllowlist": grade_allowlist,
        "contracts": {
            "preparationTarget": TARGET_SCHEMA_V2,
            "preparation": PREPARATION_CONTRACT_VERSION,
            "publication": (
                LearningCurriculumPreparationRepository
                .FORMAL_PUBLICATION_CONTRACT_VERSION
            ),
            "runtime": OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CONTRACT_VERSION,
            "runtimeClassroomSha256": classroom_contract_sha256,
            "runtimeEventBridge": FORMAL_EVENT_BRIDGE_SCHEMA,
            "runtimeEvent": FORMAL_EVENT_SCHEMA,
            "runtimeEventReceipt": FORMAL_EVENT_RECEIPT_SCHEMA,
        },
        "runtimePatch": {
            "upstreamVersion": RUNTIME_UPSTREAM_VERSION,
            "upstreamCommit": RUNTIME_UPSTREAM_COMMIT,
            "count": RUNTIME_PATCH_COUNT,
            "latest": RUNTIME_LATEST_PATCH,
            "latestSha256": RUNTIME_LATEST_PATCH_SHA256,
        },
        "gates": gates,
        "rolloutEligible": grade_allowlist == ["primary_1"] and all(gates.values()),
    }
