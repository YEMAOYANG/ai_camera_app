"""Versioned grade authority for adaptive formal classrooms.

The grade boundary is a separate field in the generation contract. Existing
teaching briefs and their hashes remain unchanged for every historical policy.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

from content.primary_skill_boundaries import boundaries_for


FORMAL_TEACHING_QUALITY_POLICY = {
    "schemaVersion": "mira.openmaic.teaching-quality-policy.v1",
    "policyId": "mira-primary-quality.v1",
    "gradeBoundaryRequired": True,
    "finalSnapshotRequired": True,
    "independentReviewRequired": True,
    "renderedScenesRequired": True,
    "maxReviewAttempts": 3,
}


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def adaptive_policy(policy: object) -> bool:
    orchestration = policy.get("skillOrchestration") if isinstance(policy, Mapping) else None
    return isinstance(orchestration, Mapping) and orchestration.get("schemaVersion") == (
        "mira.openmaic.skill-orchestration.v2"
    )


def registered_grade_boundary(*, grade_code: object, subject: object,
                              skill_id: object) -> dict[str, Any]:
    if any(not isinstance(value, str) or not value for value in (grade_code, subject, skill_id)):
        raise ValueError("formal grade boundary identity is missing")
    boundary = next((item for item in boundaries_for(grade_code, subject)
                     if item.skill_id == skill_id), None)
    if boundary is None:
        raise ValueError("formal grade boundary is not registered")
    return boundary.to_catalog_payload()


def grade_boundary_fields(course: Mapping[str, Any], policy: Mapping[str, Any]) -> dict[str, Any]:
    """Project the exact registry boundary for a newly dispatched v2 request."""

    if not adaptive_policy(policy):
        return {}
    if _sha(policy.get("teachingQuality")) != _sha(FORMAL_TEACHING_QUALITY_POLICY):
        raise ValueError("formal teaching quality policy is missing")
    boundary = registered_grade_boundary(grade_code=course.get("grade_code"),
        subject=course.get("subject"), skill_id=course.get("node_code"))
    if (course.get("boundary_version") != boundary["boundaryVersion"]
            or course.get("curriculum_version") != boundary["curriculumVersion"]):
        raise ValueError("formal course grade boundary version drifted")
    return {"gradeBoundary": boundary, "gradeBoundarySha256": _sha(boundary)}


def validate_generation_grade_boundary(generation: Mapping[str, Any],
                                      course: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Recompute new-policy grade authority; reject additions to old requests."""

    policy = generation.get("professionalCreationPolicy")
    if not adaptive_policy(policy):
        if "gradeBoundary" in generation or "gradeBoundarySha256" in generation:
            raise ValueError("historical formal request contains a new grade boundary")
        return {}
    if not isinstance(policy, Mapping) or _sha(policy.get("teachingQuality")) != _sha(FORMAL_TEACHING_QUALITY_POLICY):
        raise ValueError("formal teaching quality policy is missing")
    brief = generation.get("teachingBrief")
    identity = brief.get("course") if isinstance(brief, Mapping) else None
    if not isinstance(identity, Mapping):
        raise ValueError("formal grade boundary teaching brief is missing")
    if (brief.get("schemaVersion") != "mira.learning.formal-runtime-teaching-brief.v1"
            or generation.get("teachingBriefSha256") != _sha(brief)):
        raise ValueError("formal grade boundary teaching brief hash drifted")
    expected = registered_grade_boundary(grade_code=identity.get("gradeCode"),
        subject=identity.get("subject"), skill_id=identity.get("skillId"))
    if course is not None:
        locked = grade_boundary_fields(course, policy)
        if (locked["gradeBoundary"] != expected
                or course.get("id") != identity.get("id")
                or course.get("version") != identity.get("version")):
            raise ValueError("formal grade boundary differs from locked course")
    boundary = generation.get("gradeBoundary")
    if (not isinstance(boundary, Mapping) or _sha(boundary) != _sha(expected)
            or generation.get("gradeBoundarySha256") != _sha(expected)):
        raise ValueError("formal grade boundary payload or hash drifted")
    return {"gradeBoundary": deepcopy(dict(boundary)), "gradeBoundarySha256": _sha(expected)}
