"""Validate the actual Skill reads and per-page context of formal Pro jobs."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
import re
from typing import Any, Mapping

from integrations.openmaic_formal_pedagogy import validate_generation_grade_boundary
from integrations.openmaic_formal_skill_selection import select_formal_skills, skill_selection_plan


FORMAL_SKILL_ORCHESTRATION_POLICY = {
    "schemaVersion": "mira.openmaic.skill-orchestration.v1",
    "profileId": "mira-primary-integrated.v1",
    "skillIds": ["mira-primary-courseware", "stage-design", "k12-core-literacy-planning",
                 "deep-interactive", "slide-craft", "learning-to-learn"],
    "sceneContextRequired": True,
}
ADAPTIVE_SKILL_ORCHESTRATION_POLICY = {
    "schemaVersion": "mira.openmaic.skill-orchestration.v2",
    "profileId": "mira-primary-adaptive.v2",
    "registryId": "openmaic-builtin-skills.v1-23",
    "baseSkillIds": ["mira-primary-courseware", "stage-design", "k12-core-literacy-planning",
                     "deep-interactive", "slide-craft", "learning-to-learn"],
    "selectionMode": "server_rules",
    "mainMethodMax": 1,
    "decisionCoverageRequired": True,
    "sceneContextRequired": True,
    "gradeBoundaryRequired": True,
}
_SCHEMA = "mira.openmaic.skill-orchestration-receipt.v1"
_REFERENCE_ROOT = "k12-core-literacy-planning/references/"
_CORE_REFERENCE = _REFERENCE_ROOT + "core-literacy.md"
_SUBJECT_REFERENCES = {
    "math": _REFERENCE_ROOT + "subjects/mathematics.md",
    "chinese": _REFERENCE_ROOT + "subjects/languages.md",
    "english": _REFERENCE_ROOT + "subjects/languages.md",
}
_SHA = re.compile(r"[0-9a-f]{64}")
_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,255}")
_SCENE_TYPES = {"slide", "quiz", "interactive", "pbl"}


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def _digest(value: object) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def skill_orchestration_receipt(value: object) -> dict[str, Any]:
    fields = {"schemaVersion", "profileId", "status", "skillReads", "referenceReads",
              "sceneContexts", "receiptSha256"}
    adaptive = isinstance(value, Mapping) and value.get("schemaVersion") == "mira.openmaic.skill-orchestration-receipt.v2"
    if adaptive:
        fields.add("selectionPlan")
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("invalid formal skill receipt fields")
    receipt = deepcopy(dict(value))
    expected_schema = "mira.openmaic.skill-orchestration-receipt.v2" if adaptive else _SCHEMA
    policy = ADAPTIVE_SKILL_ORCHESTRATION_POLICY if adaptive else FORMAL_SKILL_ORCHESTRATION_POLICY
    if (receipt["schemaVersion"] != expected_schema or receipt["status"] != "succeeded"
            or receipt["profileId"] != policy["profileId"]):
        raise ValueError("invalid formal skill receipt profile")
    expected_skills = (skill_selection_plan(receipt["selectionPlan"])["selectedSkillIds"]
                       if adaptive else policy["skillIds"])
    reads = receipt["skillReads"]
    if (not isinstance(reads, list) or len(reads) != len(expected_skills)
            or any(not isinstance(item, Mapping) or set(item) != {"skillId", "sourceHash"}
                   or not _digest(item["sourceHash"]) for item in reads)
            or [item["skillId"] for item in reads] != expected_skills):
        raise ValueError("formal skill reads are incomplete")
    references = receipt["referenceReads"]
    if (not isinstance(references, list) or len(references) != 2
            or any(not isinstance(item, Mapping) or set(item) != {"resourcePath", "sourceHash"}
                   or not isinstance(item["resourcePath"], str)
                   or not _digest(item["sourceHash"]) for item in references)
            or references[0]["resourcePath"] != _CORE_REFERENCE
            or references[1]["resourcePath"] not in set(_SUBJECT_REFERENCES.values())):
        raise ValueError("formal skill reference reads are incomplete")
    contexts = receipt["sceneContexts"]
    if not isinstance(contexts, list) or not 1 <= len(contexts) <= 60:
        raise ValueError("formal skill scene contexts are missing")
    scene_ids: set[str] = set()
    for context in contexts:
        if (not isinstance(context, Mapping)
                or set(context) != {"sceneId", "sceneType", "contentContextSha256", "actionsContextSha256"}
                or not isinstance(context["sceneId"], str)
                or not _IDENTIFIER.fullmatch(context["sceneId"])
                or context["sceneId"] in scene_ids
                or not isinstance(context["sceneType"], str) or context["sceneType"] not in _SCENE_TYPES
                or not _digest(context["contentContextSha256"])
                or not _digest(context["actionsContextSha256"])):
            raise ValueError("invalid formal skill scene context")
        scene_ids.add(context["sceneId"])
    digest = receipt.pop("receiptSha256")
    if not _digest(digest) or _sha(receipt) != digest:
        raise ValueError("formal skill receipt hash mismatch")
    receipt["receiptSha256"] = digest
    return receipt


def professional_skill_fields(value: Mapping[str, Any]) -> dict[str, Any]:
    if "skillOrchestration" not in value:
        return {}
    return {"skillOrchestration": skill_orchestration_receipt(value["skillOrchestration"])}


def _bound_receipt(professional: Mapping[str, Any], generation: Mapping[str, Any]) -> dict[str, Any] | None:
    policy = generation.get("professionalCreationPolicy")
    if not isinstance(policy, Mapping):
        raise ValueError("formal skill policy is missing")
    has_policy = "skillOrchestration" in policy
    if has_policy != ("skillOrchestration" in professional):
        raise ValueError("formal skill policy and receipt mismatch")
    if not has_policy:
        return None
    if _sha(policy["skillOrchestration"]) not in {
        _sha(FORMAL_SKILL_ORCHESTRATION_POLICY), _sha(ADAPTIVE_SKILL_ORCHESTRATION_POLICY)
    }:
        raise ValueError("unsupported formal skill policy")
    unsigned = dict(professional)
    parent_digest = unsigned.pop("receiptSha256", None)
    if not _digest(parent_digest) or _sha(unsigned) != parent_digest:
        raise ValueError("formal skill parent receipt hash mismatch")
    receipt = skill_orchestration_receipt(professional["skillOrchestration"])
    adaptive = policy["skillOrchestration"]["schemaVersion"] == ADAPTIVE_SKILL_ORCHESTRATION_POLICY["schemaVersion"]
    if adaptive != (receipt["schemaVersion"] == "mira.openmaic.skill-orchestration-receipt.v2"):
        raise ValueError("formal skill receipt policy version mismatch")
    validate_generation_grade_boundary(generation)
    if adaptive:
        expected_plan = select_formal_skills(teaching_brief=generation.get("teachingBrief"),
            grade_boundary=generation.get("gradeBoundary"),
            grade_boundary_sha256=generation.get("gradeBoundarySha256"))
        if _sha(receipt["selectionPlan"]) != _sha(expected_plan):
            raise ValueError("formal skill selection plan differs from locked inputs")
    brief = generation.get("teachingBrief")
    course = brief.get("course") if isinstance(brief, Mapping) else None
    subject = course.get("subject") if isinstance(course, Mapping) else None
    if not isinstance(subject, str) or subject not in _SUBJECT_REFERENCES or receipt["referenceReads"][1]["resourcePath"] != _SUBJECT_REFERENCES[subject]:
        raise ValueError("formal skill subject reference mismatch")
    return receipt


def validate_classroom_skills(professional: Mapping[str, Any], generation: Mapping[str, Any],
                              classroom: Mapping[str, Any]) -> None:
    receipt = _bound_receipt(professional, generation)
    if receipt is None:
        return
    scenes = classroom.get("scenes")
    if (not isinstance(scenes, list) or not scenes
            or any(not isinstance(scene, Mapping) for scene in scenes)):
        raise ValueError("formal skill classroom scenes are missing")
    expected = {(scene.get("id"), scene.get("type")) for scene in scenes}
    actual = {(item["sceneId"], item["sceneType"]) for item in receipt["sceneContexts"]}
    if len(expected) != len(scenes) or expected != actual:
        raise ValueError("formal skill contexts do not cover the classroom")


def validate_skill_manifest(manifest: Mapping[str, Any]) -> None:
    professional, generation = manifest.get("professionalCreation"), manifest.get("generationContract")
    if not isinstance(professional, Mapping) or not isinstance(generation, Mapping):
        raise ValueError("formal skill authority is missing")
    receipt = _bound_receipt(professional, generation)
    if receipt is None:
        return
    evidence = manifest.get("formalEvidence")
    professional_evidence = evidence.get("professionalCreation") if isinstance(evidence, Mapping) else None
    if (not isinstance(professional_evidence, Mapping)
            or professional_evidence.get("verified") is not True
            or professional_evidence.get("receiptSha256") != professional.get("receiptSha256")
            or professional_evidence.get("skillOrchestration") != receipt):
        raise ValueError("formal skill verification evidence mismatch")
    authority = evidence.get("runtimeEventAuthority") if isinstance(evidence, Mapping) else None
    scenes = authority.get("scenes") if isinstance(authority, Mapping) else None
    contexts = receipt["sceneContexts"]
    if (not isinstance(scenes, list) or len(scenes) != len(contexts)
            or any(not isinstance(scene, Mapping) for scene in scenes)
            or {scene.get("sceneId") for scene in scenes} != {item["sceneId"] for item in contexts}
            or type(manifest.get("sceneCount")) is not int or manifest["sceneCount"] != len(contexts)):
        raise ValueError("formal skill manifest scene coverage mismatch")
    distribution = evidence.get("sceneDistribution")
    counts = Counter(item["sceneType"] for item in contexts)
    if (not isinstance(distribution, Mapping)
            or any(type(distribution.get(kind)) is not int or distribution[kind] != counts[kind]
                   for kind in _SCENE_TYPES)):
        raise ValueError("formal skill manifest scene types mismatch")
