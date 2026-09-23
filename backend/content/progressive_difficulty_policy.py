"""Registered basic difficulty for exact progressive curriculum lessons.

The classroom engine's signed difficulty envelope is shared with old courses;
the lesson scope and assessment authority here come only from the progressive
registry. No coarse objective grammar or example is used as a substitute.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from content.progressive_curriculum import (
    CURRICULUM_VERSION,
    curriculum_identity,
    lesson_by_id,
)


DIFFICULTY_POLICY_SCHEMA = "mira.learning.difficulty-policy.v1"
PROGRESSIVE_DIFFICULTY_POLICY_VERSION = "mira.learning.progressive-difficulty-policy.v1"


def _sha256(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def progressive_difficulty_policy(
    grade_code: str, subject: str, lesson_id: str, difficulty_code: str = "basic",
) -> dict:
    """Return the signed, reproducible authority for this registered basic lesson."""
    lesson = lesson_by_id(lesson_id)
    if lesson["gradeCode"] != grade_code or lesson["subject"] != subject:
        raise ValueError("progressive difficulty grade, subject and lesson must match")
    if difficulty_code != "basic":
        raise ValueError("progressive lessons require explicitly registered basic difficulty")
    constraints = lesson["constraints"]
    objective = lesson["assessmentMode"] == "objective"
    value = {
        "schemaVersion": DIFFICULTY_POLICY_SCHEMA,
        "policyVersion": PROGRESSIVE_DIFFICULTY_POLICY_VERSION,
        "gradeCode": grade_code,
        "subject": subject,
        "skillId": lesson_id,
        "difficultyCode": "basic",
        "curriculumVersion": CURRICULUM_VERSION,
        "curriculumIdentitySha256": curriculum_identity()["datasetSha256"],
        "lessonSha256": _sha256(lesson),
        "objectiveRuleVersion": "mira.learning.progressive-host-validation.v1",
        "mode": "progressive_objective" if objective else "progressive_observed",
        "lessonScope": {
            "unitId": lesson["unitId"],
            "unitTitle": lesson["unitTitle"],
            "sourceStepTitle": lesson["sourceStepTitle"],
            "learningObjectives": deepcopy(lesson["learningObjectives"]),
            "introducedKnowledgeIds": deepcopy(lesson["introducedKnowledgeIds"]),
            "prerequisiteLessonIds": deepcopy(lesson["prerequisiteLessonIds"]),
            "constraints": deepcopy(constraints),
        },
        "complexity": {
            "scope": "current_grade_current_lesson",
            "reasoningScope": "direct_application_of_taught_lesson_objectives",
            "maxCoreNewTargets": constraints["maxCoreNewTargets"],
            "assessmentOperation": "independent_lesson_tasks" if objective else "parent_observation",
            "requirements": [
                "basic means the entry level of this grade and this lesson, not a restart at grade 1.",
                "Teach and demonstrate the declared lesson objectives before guided practice and assessment.",
                "Use prerequisites only to support this lesson; do not replace it with another grade or coarse skill.",
                "Do not add future lesson skills, harder unit-wide reasoning, vocabulary, grammar or operations outside the locked scope.",
                "Different assessment set ordinals change task material, never the difficulty or lesson boundary.",
            ],
        },
        "assessment": {
            "mode": lesson["assessmentMode"],
            "criteria": deepcopy(lesson["assessmentCriteria"]),
            "evidenceKinds": deepcopy(constraints["assessmentEvidenceKinds"]),
            "autoMasteryEligible": objective,
            "manualConfirmationRequired": not objective,
            "semanticScoringAuthority": "independent_answer_blind_review" if objective else "none",
        },
    }
    value["policySha256"] = _sha256(value)
    return value
