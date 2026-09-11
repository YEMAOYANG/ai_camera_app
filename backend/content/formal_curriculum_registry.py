"""Grade-specific formal curriculum authority; Grade 1 stays byte-for-byte frozen.

Grades 2–6 cover only the explicitly registered objective pilot boundaries.
Having a code authority does not authorize production, spend, or publication.
"""
from __future__ import annotations

import copy
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Mapping

from content.primary_skill_boundaries import (
    PRIMARY_CURRICULUM_VERSION, SUBJECT_LANGUAGE_POLICY_VERSION,
    boundaries_for, primary_one_content_contract,
)
from content.formal_difficulty_policy import DIFFICULTY_CODES, DIFFICULTY_SLOT_MANIFEST
from content.formal_objective_rules import (
    CLOSED_ASSESSMENT_TYPES, OBJECTIVE_RULE_VERSION, objective_question_policy,
)

FORMAL_GRADE_CODES = tuple(f"primary_{n}" for n in range(1, 7))
FORMAL_SUBJECTS = ("chinese", "math", "english")
REGISTRY_VERSION = "mira.learning.formal-curriculum-registry.v2"
_MANIFEST_PATH = Path(__file__).with_name("formal_curriculum_authority.v2.json")


def formal_supported_grade_codes() -> tuple[str, ...]:
    return FORMAL_GRADE_CODES


def require_formal_grade(grade_code: object) -> str:
    if not isinstance(grade_code, str) or grade_code not in FORMAL_GRADE_CODES:
        raise ValueError("unregistered formal grade")
    return grade_code


def _hash(value: Mapping) -> str:
    payload = dict(value); payload.pop("datasetSha256", None)
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _build_registered_contract(grade_code: str) -> dict:
    subjects = []
    inventories = {}
    canaries = []
    for subject_ordinal, subject in enumerate(FORMAL_SUBJECTS, 1):
        registered = boundaries_for(grade_code, subject)
        if not registered: raise ValueError("formal grade lacks registered subject")
        boundary_rows = []
        seen = set()
        for ordinal, boundary in enumerate(registered, 1):
            if any(prerequisite not in seen for prerequisite in boundary.prerequisite_skills):
                raise ValueError("formal prerequisites must be acyclic and subject-local")
            seen.add(boundary.skill_id)
            key = f"{grade_code}.{subject}.{boundary.skill_id}.objective.v1"
            inventories[key] = {
                "schemaVersion": key, "kind": "registered_objective_rules",
                "rules": objective_question_policy(grade_code,subject,boundary.skill_id),
                "difficultyPolicies": {code: objective_question_policy(grade_code,subject,boundary.skill_id,code) for code in DIFFICULTY_CODES},
                "boundary": boundary.to_catalog_payload(),
            }
            boundary_rows.append({
                "skillId": boundary.skill_id, "boundaryOrdinal": ordinal,
                "prerequisiteSkills": list(boundary.prerequisite_skills),
                "validationInventoryKeys": [key],
                "difficultySlots": copy.deepcopy(list(DIFFICULTY_SLOT_MANIFEST)),
            })
        target_language = "en-US" if subject == "english" else "zh-CN"
        subjects.append({
            "subject": subject, "subjectOrdinal": subject_ordinal,
            "instructionLanguageCode": "zh-CN", "targetLanguageCode": target_language,
            "boundaries": boundary_rows,
        })
        canaries.append({
            "subject": subject, "subjectOrdinal": subject_ordinal,
            "skillId": registered[0].skill_id, "boundaryOrdinal": 1,
            "variantOrdinal": 1, "difficultyCode": "standard",
        })
    number = grade_code.rsplit("_",1)[1]
    contract = {
        "schemaVersion": f"mira.learning.primary-{number}-content-validation.v2",
        "registryVersion": REGISTRY_VERSION, "gradeCode": grade_code,
        "curriculumVersion": PRIMARY_CURRICULUM_VERSION,
        "subjectLanguagePolicyVersion": SUBJECT_LANGUAGE_POLICY_VERSION,
        "coverage": "registered_objective_pilot_only",
        "publicationRequires": ["explicit_supply_scope", "paid_budget_reservation", "formal_host_receipt", "media_ready", "teaching_acceptance"],
        "closedAssessmentTypes": list(CLOSED_ASSESSMENT_TYPES),
        "objectiveRuleVersion": OBJECTIVE_RULE_VERSION,
        "subjects": subjects, "inventories": inventories,
        "canaryManifest": {"version": f"mira.learning.primary-{number}-canary.v2", "targets": canaries},
    }
    contract["datasetSha256"] = _hash(contract)
    return contract


@lru_cache(maxsize=6)
def _load_content_contract(grade_code: str) -> dict:
    require_formal_grade(grade_code)
    if grade_code == "primary_1": return primary_one_content_contract()
    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    contract = _build_registered_contract(grade_code)
    if manifest.get("schemaVersion") != REGISTRY_VERSION or manifest.get("grades",{}).get(grade_code) != contract["datasetSha256"]:
        raise ValueError("sealed grade content authority changed without a manifest version")
    return contract


def formal_content_contract(grade_code: str) -> dict:
    return copy.deepcopy(_load_content_contract(grade_code))


def formal_content_validation_identity(grade_code: str) -> dict[str, str]:
    contract = formal_content_contract(grade_code)
    number = grade_code.rsplit("_",1)[1]
    version = "v1" if grade_code == "primary_1" else "v2"
    return {
        "contentValidationContractVersion": contract["schemaVersion"],
        "contentValidationDatasetSha256": contract["datasetSha256"],
        "subjectLanguagePolicyVersion": contract["subjectLanguagePolicyVersion"],
        "hostGateVersion": f"mira.learning.primary-{number}-host-gate.{version}",
        "hostGateReceiptSchemaVersion": f"mira.learning.primary-{number}-host-gate-receipt.{version}",
        "hostGateEvidenceSchemaVersion": f"mira.learning.primary-{number}-host-gate-evidence.{version}",
        "hostFingerprintVersion": f"mira.learning.primary-{number}-semantic-fingerprint.{version}",
        "hostFingerprintPayloadSchemaVersion": f"mira.learning.primary-{number}-semantic-fingerprint-payload.{version}",
    }


def formal_registered_boundary(grade_code: str, subject: str, skill_id: str):
    require_formal_grade(grade_code)
    formal_content_contract(grade_code)
    found = next((b for b in boundaries_for(grade_code, subject) if b.skill_id == skill_id),None)
    if found is None: raise ValueError("unregistered formal grade/subject/skill")
    return found


def formal_slot_difficulty(grade_code: str, subject: str, skill_id: str, variant_ordinal: int) -> str | None:
    if grade_code == 'primary_1': return None
    contract = formal_content_contract(grade_code)
    for subject_policy in contract['subjects']:
        if subject_policy['subject'] != subject: continue
        for boundary in subject_policy['boundaries']:
            if boundary['skillId'] != skill_id: continue
            for slot in boundary['difficultySlots']:
                if slot['variantOrdinal'] == variant_ordinal: return slot['difficultyCode']
    raise ValueError('formal difficulty slot is not registered')
