from __future__ import annotations

import hashlib
import json
import re
from typing import Mapping

from content.formal_curriculum_registry import (
    formal_content_contract, formal_content_validation_identity,
    require_formal_grade,
)

from content.primary_skill_boundaries import (
    CONTENT_VALIDATION_CONTRACT_VERSION,
    PRIMARY_CURRICULUM_VERSION,
    PRIMARY_ONE_CANARY_MANIFEST_VERSION,
    PRIMARY_SKILL_BOUNDARIES,
    SUBJECT_LANGUAGE_POLICY_VERSION,
    primary_one_content_contract,
)
from content.teacher_profiles import (
    FORMAL_SUBJECT_QWEN_VOICE_CONTRACT_VERSION,
    TEACHER_REGISTRY_VERSION,
    get_formal_subject_qwen_voice_identity,
    get_teacher_profile,
)
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient
from integrations.openmaic_formal_media import VIDEO_CONTENT_PROVIDER_PROFILE
from services.lesson_package_validator import (
    FORMAL_RUNTIME_PACKAGE_COMPILER_VERSION,
    FORMAL_RUNTIME_PACKAGE_SCHEMA,
    FORMAL_RUNTIME_PACKAGE_SOURCE_SCHEMA,
    FORMAL_RUNTIME_TEACHING_BRIEF_SCHEMA,
    LESSON_PACKAGE_COMPILER_VERSION,
)
from services.learning_question_phase_contract import QUESTION_CONTRACT_VERSION
from services.openmaic_full_runtime_service import (
    OpenMaicFullRuntimeService,
)


PREPARATION_SCHEMA_VERSION = "mira.learning.preparation.v1"
PREPARATION_SCHEMA_V2 = "mira.learning.preparation.v2"
PREPARATION_SCHEMA_HEADER = "X-Mira-Preparation-Schema"
TARGET_SCHEMA_V1 = "mira.learning.preparation-target.v1"
TARGET_SCHEMA_V2 = "mira.learning.preparation-target.v2"
PREPARATION_CONTRACT_VERSION = "mira.learning.grade-preparation.v1"
VARIANTS_PER_BOUNDARY = 3
MAX_PARENT_RETRIES = 1
PREPARATION_SUBJECTS = ("chinese", "math", "english")
FORMAL_SUBJECT_TEACHERS = {
    "chinese": "mira_chinese_gentle",
    "math": "mira_math_clear",
    "english": "mira_english_standard",
}
FORMAL_SUBJECT_VOICE_CONTRACT_VERSION = FORMAL_SUBJECT_QWEN_VOICE_CONTRACT_VERSION
FORMAL_AUDIO_CONTRACT_VERSION = "mira.learning.formal-qwen-audio.v1"
FORMAL_PCM_VALIDATION_CONTRACT_VERSION = (
    "mira.learning.formal-pcm-validation.v1"
)
FORMAL_ASR_ROUNDTRIP_CONTRACT_VERSION = (
    "mira.learning.formal-qwen-asr-roundtrip.v1"
)
CONTENT_PROVIDER_PROFILE_CONTRACT_VERSION = (
    # v96 makes OpenMAIC the sole learning-courseware generation authority and
    # treats definitive Provider 4xx responses as safe, non-retryable failures.
    # The backend retains no learning Kimi endpoint/key, while the later
    # classroom stage compiles this same generated artifact.
    # v99 preserves each generated candidate's concrete display title through
    # Host-sealed lesson-text compilation. The bump forces a fresh target/build
    # instead of mixing already-persisted v98 checkpoints with the new rule.
    # v100 binds OpenMAIC's single, bounded retry for a definitive upstream
    # HTTP 429. The exact Provider request and shared timeout are reused; all
    # other 4xx responses remain terminal and maxRetries stays disabled.
    # v103 keeps request-specific scenario titles NFKC-stable so Host replay
    # never spends a second Provider call repairing punctuation-only drift.
    # v104 binds the professional DeepSeek creator/verifier policy so no
    # Kimi-era checkpoint can be reused by the new target fingerprint.
    # v105 preserves that policy while opening a fresh idempotency scope after
    # a v104 Provider connection interruption was sealed as ambiguous.
    # v106 adds a bounded HappyHorse video policy to new targets; compatibility
    # keeps every v105 target and dispatch body frozen for old queues.
    VIDEO_CONTENT_PROVIDER_PROFILE
)
FORMAL_AUDIO_SEGMENT_COUNT_POLICY = {
    "derivedFrom": "runtime_speech_action_count",
    "min": 1,
    "max": 240,
}

FORMAL_RUNTIME_CONTRACT_VERSION = "|".join(
    (
        OpenMaicFullRuntimeClient.FORMAL_RUNTIME_VERSION,
        OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CONTRACT_VERSION,
        OpenMaicFullRuntimeService.MANIFEST_SCHEMA,
        FORMAL_RUNTIME_PACKAGE_SCHEMA,
        FORMAL_RUNTIME_PACKAGE_COMPILER_VERSION,
        FORMAL_RUNTIME_PACKAGE_SOURCE_SCHEMA,
        FORMAL_RUNTIME_TEACHING_BRIEF_SCHEMA,
    )
)


def build_preparation_target(grade_code: str) -> dict[str, object]:
    normalized = str(grade_code or "").strip()
    if normalized not in {f"primary_{grade}" for grade in range(1, 7)}:
        raise ValueError("unsupported primary grade")

    boundaries = [
        boundary
        for boundary in PRIMARY_SKILL_BOUNDARIES
        if boundary.grade_code == normalized
    ]
    primary_one_authority = formal_content_contract(normalized)
    validation_identity = formal_content_validation_identity(normalized)
    if primary_one_authority is not None:
        registered = {
            (boundary.subject, boundary.skill_id): boundary
            for boundary in boundaries
        }
        boundary_targets = []
        for subject_policy in primary_one_authority["subjects"]:
            for authority_boundary in subject_policy["boundaries"]:
                boundary = registered[
                    (subject_policy["subject"], authority_boundary["skillId"])
                ]
                boundary_targets.append(
                    {
                        "subject": boundary.subject,
                        "subjectOrdinal": subject_policy["subjectOrdinal"],
                        "skillId": boundary.skill_id,
                        "boundaryOrdinal": authority_boundary["boundaryOrdinal"],
                        "boundaryVersion": boundary.boundary_version,
                        "variantOrdinals": list(
                            range(1, VARIANTS_PER_BOUNDARY + 1)
                        ),
                    }
                )
    else:
        boundary_targets = sorted(
            (
                {
                    "subject": boundary.subject,
                    "skillId": boundary.skill_id,
                    "boundaryVersion": boundary.boundary_version,
                }
                for boundary in boundaries
            ),
            key=lambda item: (item["subject"], item["skillId"]),
        )
    subject_targets = {
        subject: {
            "boundaryCount": sum(
                1 for boundary in boundaries if boundary.subject == subject
            ),
            "totalCourseCount": sum(
                1 for boundary in boundaries if boundary.subject == subject
            )
            * VARIANTS_PER_BOUNDARY,
        }
        for subject in PREPARATION_SUBJECTS
    }
    if any(item["boundaryCount"] <= 0 for item in subject_targets.values()):
        raise ValueError("primary grade target must include all three subjects")

    teacher_targets = {}
    for subject in PREPARATION_SUBJECTS:
        profile = get_teacher_profile(FORMAL_SUBJECT_TEACHERS[subject])
        formal_voice = get_formal_subject_qwen_voice_identity(subject)
        if profile.subject != subject:
            raise ValueError("teacher target subject mismatch")
        teacher_targets[subject] = {
            "teacherProfile": {
                "id": profile.profile_id,
                "version": profile.version,
                "languageCode": profile.language_code,
                "avatarPath": profile.avatar_path,
            },
            "formalVoiceSelection": formal_voice.to_target_payload(),
        }

    formal_primary_one_fields: dict[str, object] = {}
    if primary_one_authority is not None:
        language_policies = {
            subject_policy["subject"]: {
                "subjectOrdinal": subject_policy["subjectOrdinal"],
                "instructionLanguageCode": subject_policy[
                    "instructionLanguageCode"
                ],
                "targetLanguageCode": subject_policy["targetLanguageCode"],
            }
            for subject_policy in primary_one_authority["subjects"]
        }
        course_targets = []
        for boundary_target in boundary_targets:
            language_policy = language_policies[boundary_target["subject"]]
            for variant_ordinal in boundary_target["variantOrdinals"]:
                course_targets.append(
                    {
                        "subject": boundary_target["subject"],
                        "subjectOrdinal": boundary_target["subjectOrdinal"],
                        "skillId": boundary_target["skillId"],
                        "boundaryOrdinal": boundary_target["boundaryOrdinal"],
                        "boundaryVersion": boundary_target["boundaryVersion"],
                        "variantOrdinal": variant_ordinal,
                        "instructionLanguageCode": language_policy[
                            "instructionLanguageCode"
                        ],
                        "targetLanguageCode": language_policy[
                            "targetLanguageCode"
                        ],
                    }
                )
        if normalized != "primary_1":
            from content.formal_curriculum_registry import formal_slot_difficulty
            for course_target in course_targets:
                course_target["difficultyCode"] = formal_slot_difficulty(normalized, course_target["subject"], course_target["skillId"], course_target["variantOrdinal"])
        boundary_by_identity = {
            (item["subject"], item["skillId"]): item
            for item in boundary_targets
        }
        canary_targets = []
        for canary in primary_one_authority["canaryManifest"]["targets"]:
            boundary = boundary_by_identity[(canary["subject"], canary["skillId"])]
            canary_targets.append(
                {
                    **canary,
                    "boundaryVersion": boundary["boundaryVersion"],
                }
            )
        formal_primary_one_fields = {
            "contentGenerationContractVersion": QUESTION_CONTRACT_VERSION,
            "contentProviderProfileContractVersion": (
                CONTENT_PROVIDER_PROFILE_CONTRACT_VERSION
            ),
            "contentValidationContractVersion": validation_identity["contentValidationContractVersion"],
            "contentValidationDatasetSha256": primary_one_authority[
                "datasetSha256"
            ],
            "subjectLanguagePolicyVersion": SUBJECT_LANGUAGE_POLICY_VERSION,
            "subjectLanguagePolicies": language_policies,
            "courseTargets": course_targets,
            "canaryManifest": {
                "version": primary_one_authority["canaryManifest"]["version"],
                "targets": canary_targets,
            },
            "formalRuntimePackageContract": {
                "schemaVersion": FORMAL_RUNTIME_PACKAGE_SCHEMA,
                "compilerVersion": FORMAL_RUNTIME_PACKAGE_COMPILER_VERSION,
                "sourceSchemaVersion": FORMAL_RUNTIME_PACKAGE_SOURCE_SCHEMA,
                "teachingBriefSchemaVersion": (
                    FORMAL_RUNTIME_TEACHING_BRIEF_SCHEMA
                ),
            },
            "formalRuntimePolicy": {
                "runtimeVersion": OpenMaicFullRuntimeClient.FORMAL_RUNTIME_VERSION,
                "runtimeContractVersion": (
                    OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CONTRACT_VERSION
                ),
                "upstreamIdempotencyKey": "runtimeRequestId",
                "queryByRuntimeRequestId": True,
                "speechAudioGenerated": True,
                "enableTTS": False,
                "enableWebSearch": True,
                "coursewareAuthority": dict(
                    OpenMaicFullRuntimeClient.COURSEWARE_AUTHORITY
                ),
                "professionalModelPolicy": json.loads(
                    json.dumps(
                        OpenMaicFullRuntimeClient.FORMAL_PROFESSIONAL_MODEL_POLICY,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                ),
                "professionalCreationPolicy": json.loads(
                    json.dumps(
                        OpenMaicFullRuntimeClient.FORMAL_PROFESSIONAL_CREATION_POLICY,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                ),
            },
        }

    return {
        "schemaVersion": (
            TARGET_SCHEMA_V2
            if primary_one_authority is not None
            else TARGET_SCHEMA_V1
        ),
        "preparationContractVersion": PREPARATION_CONTRACT_VERSION,
        "gradeCode": normalized,
        "subjects": list(PREPARATION_SUBJECTS),
        "curriculumVersion": PRIMARY_CURRICULUM_VERSION,
        "boundaries": boundary_targets,
        "boundaryVersions": [
            item["boundaryVersion"] for item in boundary_targets
        ],
        "boundaryCount": len(boundary_targets),
        "subjectTargets": subject_targets,
        "variantsPerBoundary": VARIANTS_PER_BOUNDARY,
        "totalCourseCount": len(boundary_targets) * VARIANTS_PER_BOUNDARY,
        **(
            {}
            if primary_one_authority is not None
            else {"lessonPackageCompilerVersion": LESSON_PACKAGE_COMPILER_VERSION}
        ),
        "teacherRegistryVersion": TEACHER_REGISTRY_VERSION,
        "formalSubjectVoiceContractVersion": FORMAL_SUBJECT_VOICE_CONTRACT_VERSION,
        "formalAudioContracts": {
            "audio": FORMAL_AUDIO_CONTRACT_VERSION,
            "pcmValidation": FORMAL_PCM_VALIDATION_CONTRACT_VERSION,
            "asrRoundTrip": FORMAL_ASR_ROUNDTRIP_CONTRACT_VERSION,
            "expectedSegmentCount": FORMAL_AUDIO_SEGMENT_COUNT_POLICY,
        },
        "teacherTargets": teacher_targets,
        "fullRuntimeContractVersion": FORMAL_RUNTIME_CONTRACT_VERSION,
        "formalRuntimeClassroomContract": json.loads(
            json.dumps(
                OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CLASSROOM_CONTRACT,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        ),
        **formal_primary_one_fields,
    }


def preparation_target_fingerprint(target: Mapping[str, object]) -> str:
    canonical = json.dumps(
        dict(target), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def preparation_authority_grade(authority: object) -> str:
    """Read an explicit grade from frozen target/plan/build authority only."""
    if isinstance(authority, str):
        if authority.startswith("{"):
            return preparation_authority_grade(json.loads(authority))
        return require_formal_grade(authority)
    if not isinstance(authority, Mapping):
        raise ValueError("formal preparation authority is missing")
    direct = authority.get("gradeCode", authority.get("grade_code"))
    nested = authority.get("target_spec_json", authority.get("targetSpec"))
    if nested is not None:
        nested_grade = preparation_authority_grade(nested)
        if direct is not None and direct != nested_grade:
            raise ValueError("formal preparation authority grade drift")
        return nested_grade
    return require_formal_grade(direct)


def canonical_preparation_target_for(authority: object) -> dict[str, object]:
    return build_preparation_target(preparation_authority_grade(authority))


def formal_target_course_count(authority: object) -> int:
    target = canonical_preparation_target_for(authority)
    return len(target["courseTargets"])


def compatible_preparation_scope_sql(
    current: Mapping[str, object], *, target_column: str, fingerprint_column: str,
    automatic_only: bool = False,
) -> tuple[str, tuple[object, ...]]:
    """Select exact target/hash pairs while keeping each job's frozen identity."""
    from integrations.openmaic_formal_media import (
        INTEGRATED_PROFESSIONAL_POLICY, PROFESSIONAL_POLICY,
        compatible_preparation_targets, policy_from_target,
    )

    for column in (target_column, fingerprint_column):
        if type(column) is not str or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?", column) is None:
            raise ValueError("preparation scope column is invalid")
    clauses = []
    params: list[object] = []
    for target in compatible_preparation_targets(current):
        # An upgrade must not awaken older, dormant paid-generation queues.
        # Keep both previously active integrated/adaptive scopes plus the new
        # video scope. Older contracts remain valid only for explicit recovery.
        if automatic_only and target != current and policy_from_target(target) not in (
            INTEGRATED_PROFESSIONAL_POLICY, PROFESSIONAL_POLICY
        ):
            continue
        clauses.append(f"({target_column} = ? AND {fingerprint_column} = ?)")
        params.extend((json.dumps(target, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                       preparation_target_fingerprint(target)))
    return "(" + " OR ".join(clauses) + ")", tuple(params)
