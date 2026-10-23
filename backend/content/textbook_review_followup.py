"""Bind complete-scene review follow-ups to the current quality policy.

The native revision operator preserves its original frozen authoring contract.
This module reads that operator's immutable archive and produces a small,
sealed bridge for a later preview/publication review.  It never mutates the
candidate, revision archive, database, or a published release.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from content.textbook_catalog import canonical, digest
from content.textbook_interaction_policy import freeze_interaction_policy
from content.textbook_scene_contract import scene_canonical, scene_digest


SCHEMA = "mira.textbook.complete-scene-review-followup.v1"
STATUS = "quality_review_required"
VERIFICATION = "sealed_complete_scene_revision_chain_and_current_candidate"
PLAN_SCHEMA = "mira.textbook.current-review-revision-plan.v1"
RECEIPT_SCHEMA = "mira.textbook.current-review-revision-receipt.v1"
REVISION_VERIFICATION = "static_review_only_not_play_audio_or_publication"
SHA = re.compile(r"^[a-f0-9]{64}$")

FOLLOWUP_FIELDS = {
    "schemaVersion", "status", "verification", "sessionId", "stageId",
    "baseInteractionPolicyVersion", "baseInteractionPolicySha256",
    "currentInteractionPolicyVersion", "currentInteractionPolicySha256",
    "wholeCourseQualityContractSha256", "candidateSourceSha256", "candidateSha256",
    "candidateFileSha256", "revisionIds", "revisionReceiptSha256s",
    "completeSceneIds", "sha256",
}
PLAN_FIELDS = {
    "schemaVersion", "verification", "input", "dataDir", "sessionId", "stageId",
    "ownerFingerprint", "contractSha256", "beforeDocumentSha256",
    "afterDocumentSha256", "beforeCandidateSha256", "beforeCandidateFileSha256",
    "afterCandidateSha256", "afterCandidateFileSha256", "assetAdditions",
    "stateTransitionNotes", "revisions", "sha256",
}
RECEIPT_FIELDS = {
    "schemaVersion", "revisionId", "status", "verification", "sessionId",
    "stageId", "planSha256", "documentSha256", "candidateSha256",
    "candidateFileSha256", "stateTransitionNotes", "revisions",
    "assetAdditions", "providerCalls", "sha256",
}


def _is_sha(value):
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def _read(path, root):
    path = Path(path)
    try:
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("revision evidence escaped its managed root")
        for item in (path, *path.parents):
            if item == root:
                break
            if item.is_symlink():
                raise ValueError("revision evidence cannot use symbolic links")
        raw = path.read_bytes()
        value = json.loads(raw, object_pairs_hook=_unique_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(value, dict):
            raise ValueError("revision evidence is not an object")
        return value, raw
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("revision evidence is missing or invalid") from error


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def _sealed(value, fields, schema):
    allowed = fields if isinstance(fields, tuple) else (fields,)
    if (not isinstance(value, dict) or set(value) not in allowed
            or value.get("schemaVersion") != schema or not _is_sha(value.get("sha256"))
            or digest({key: item for key, item in value.items() if key != "sha256"}) != value["sha256"]):
        raise ValueError("revision evidence seal is invalid")


def _candidate_file(path, root, session_id, stage_id):
    value, raw = _read(path, root)
    if (value.get("schemaVersion") != "mira.textbook.authoring-candidate.v1"
            or value.get("sessionId") != session_id or value.get("stageId") != stage_id
            or not _is_sha(value.get("sha256"))
            or digest({key: item for key, item in value.items() if key != "sha256"}) != value["sha256"]):
        raise ValueError("revision candidate identity is invalid")
    return value, raw


def _scene_record_matches(record, scene):
    try:
        saved = json.loads(record.get("canonicalJson"), object_pairs_hook=_unique_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        return (record.get("sceneId") == scene.get("id")
                and record.get("sha256") == hashlib.sha256(record["canonicalJson"].encode()).hexdigest()
                and scene_canonical(saved) == scene_canonical(scene))
    except (TypeError, ValueError, json.JSONDecodeError):
        return False


def _complete_scene_ids(entry, root, stage_id, contract_sha256):
    result = []
    for revision in entry["plan"]["revisions"]:
        if not isinstance(revision, dict) or not isinstance(revision.get("sceneId"), str):
            raise ValueError("revision scene evidence is invalid")
        evidence = revision.get("completeSceneEvidence")
        if evidence is None:
            continue
        required = {
            "exactSceneId", "frozenContractSha256", "originalSceneSha256",
            "currentSceneSha256", "replacementSceneSha256", "preservedIdentity",
            "reason", "originalSceneFileSha256", "replacementSceneFileSha256",
            "assetAdditions",
        }
        if (not isinstance(evidence, dict) or set(evidence) != required
                or evidence.get("exactSceneId") != revision["sceneId"]
                or evidence.get("frozenContractSha256") != contract_sha256
                or evidence.get("currentSceneSha256") != revision.get("beforeSceneSha256")
                or evidence.get("replacementSceneSha256") != revision.get("afterSceneSha256")
                or any(not _is_sha(evidence.get(field)) for field in
                       ("originalSceneSha256", "currentSceneSha256", "replacementSceneSha256",
                        "originalSceneFileSha256", "replacementSceneFileSha256"))
                or not isinstance(evidence.get("reason"), str) or not evidence["reason"].strip()
                or not isinstance(evidence.get("assetAdditions"), list)):
            raise ValueError("complete-scene revision evidence is invalid")
        suffix = hashlib.sha256(revision["sceneId"].encode()).hexdigest()
        declared, declared_raw = _read(root / f"declared-original-scene-{suffix}.json", root)
        replacement, replacement_raw = _read(root / f"replacement-scene-{suffix}.json", root)
        before, _ = _read(root / f"original-scene-{suffix}.json", root)
        if (hashlib.sha256(declared_raw).hexdigest() != evidence["originalSceneFileSha256"]
                or hashlib.sha256(replacement_raw).hexdigest() != evidence["replacementSceneFileSha256"]
                or scene_digest(declared) != evidence["originalSceneSha256"]
                or scene_digest(replacement) != evidence["replacementSceneSha256"]
                or scene_digest(before) != revision.get("beforeSceneSha256")
                or any(scene.get("id") != revision["sceneId"] or scene.get("stageId") != stage_id
                       for scene in (declared, replacement, before))):
            raise ValueError("complete-scene archived bytes differ from the sealed revision")
        result.append(revision["sceneId"])
    return result


def _revision_entry(folder, stage_root, session_id, stage_id, contract_sha256):
    if folder.is_symlink() or not folder.is_dir() or not _is_sha(folder.name):
        raise ValueError("revision archive directory is invalid")
    plan, _ = _read(folder / "intent.json", stage_root)
    receipt, _ = _read(folder / "receipt.json", stage_root)
    _sealed(plan, (PLAN_FIELDS, PLAN_FIELDS - {"assetAdditions"}), PLAN_SCHEMA)
    _sealed(receipt, (RECEIPT_FIELDS, RECEIPT_FIELDS - {"assetAdditions"}), RECEIPT_SCHEMA)
    input_value = plan.get("input")
    if (plan["sha256"] != folder.name or plan.get("verification") != REVISION_VERIFICATION
            or plan.get("sessionId") != session_id or plan.get("stageId") != stage_id
            or plan.get("contractSha256") != contract_sha256
            or not isinstance(input_value, dict) or input_value.get("stageId") != stage_id
            or input_value.get("expectedCandidateSha256") != plan.get("beforeCandidateSha256")
            or input_value.get("expectedCandidateFileSha256") != plan.get("beforeCandidateFileSha256")
            or any(not _is_sha(plan.get(field)) for field in
                   ("beforeCandidateSha256", "beforeCandidateFileSha256",
                    "afterCandidateSha256", "afterCandidateFileSha256"))
            or receipt.get("revisionId") != plan["sha256"]
            or receipt.get("planSha256") != plan["sha256"]
            or receipt.get("status") != "static_candidate_review_revised"
            or receipt.get("verification") != REVISION_VERIFICATION
            or receipt.get("sessionId") != session_id or receipt.get("stageId") != stage_id
            or receipt.get("documentSha256") != plan.get("afterDocumentSha256")
            or receipt.get("candidateSha256") != plan.get("afterCandidateSha256")
            or receipt.get("candidateFileSha256") != plan.get("afterCandidateFileSha256")
            or receipt.get("stateTransitionNotes") != plan.get("stateTransitionNotes")
            or receipt.get("revisions") != plan.get("revisions")
            or receipt.get("assetAdditions", []) != plan.get("assetAdditions", [])
            or receipt.get("providerCalls") != 0):
        raise ValueError("revision plan and receipt identities differ")
    original, original_raw = _candidate_file(folder / "original-candidate.json", stage_root,
                                              session_id, stage_id)
    if (original["sha256"] != plan["beforeCandidateSha256"]
            or hashlib.sha256(original_raw).hexdigest() != plan["beforeCandidateFileSha256"]):
        raise ValueError("revision original candidate differs from the plan")
    return {"plan": plan, "receipt": receipt,
            "completeSceneIds": _complete_scene_ids({"plan": plan}, folder, stage_id, contract_sha256)}


def validate_complete_scene_review_followup(value, *, candidate_source_sha256, candidate=None,
                                             current_policy=None):
    """Validate a frozen bridge.  A live policy is optional for release reads."""
    _sealed(value, FOLLOWUP_FIELDS, SCHEMA)
    if (value.get("status") != STATUS or value.get("verification") != VERIFICATION
            or not _is_sha(candidate_source_sha256)
            or value.get("candidateSourceSha256") != candidate_source_sha256
            or type(value.get("baseInteractionPolicyVersion")) is not int
            or type(value.get("currentInteractionPolicyVersion")) is not int
            or value["baseInteractionPolicyVersion"] < 1
            or value["currentInteractionPolicyVersion"] < 2
            or any(not _is_sha(value.get(field)) for field in
                   ("baseInteractionPolicySha256", "currentInteractionPolicySha256",
                    "wholeCourseQualityContractSha256", "candidateSha256",
                    "candidateFileSha256"))
            or not isinstance(value.get("revisionIds"), list) or not value["revisionIds"]
            or not isinstance(value.get("revisionReceiptSha256s"), list)
            or len(value["revisionReceiptSha256s"]) != len(value["revisionIds"])
            or any(not _is_sha(item) for item in value["revisionIds"] + value["revisionReceiptSha256s"])
            or len(set(value["revisionIds"])) != len(value["revisionIds"])
            or not isinstance(value.get("completeSceneIds"), list) or not value["completeSceneIds"]
            or any(not isinstance(item, str) or not item for item in value["completeSceneIds"])
            or len(set(value["completeSceneIds"])) != len(value["completeSceneIds"])):
        raise ValueError("complete-scene review follow-up is invalid")
    if candidate is not None and (candidate.get("interactionPolicyVersion") != value["baseInteractionPolicyVersion"]
            or candidate.get("interactionPolicySha256") != value["baseInteractionPolicySha256"]
            or candidate.get("sha256") != value["candidateSha256"]):
        raise ValueError("complete-scene follow-up differs from its authoring candidate")
    if current_policy is not None:
        policy = current_policy.get("policy") if isinstance(current_policy, dict) else None
        contract = policy.get("wholeCourseQualityContract") if isinstance(policy, dict) else None
        if (not isinstance(contract, dict)
                or current_policy.get("sha256") != value["currentInteractionPolicySha256"]
                or policy.get("version") != value["currentInteractionPolicyVersion"]
                or digest(contract) != value["wholeCourseQualityContractSha256"]):
            raise ValueError("complete-scene follow-up is not bound to the current quality policy")
    return value


def discover_complete_scene_review_followup(classroom, classroom_directory, *, session_id, stage_id,
                                              base_policy_version, base_policy_sha256,
                                              candidate_source_sha256=None):
    """Return a sealed bridge when the current candidate descends from a complete-scene revision."""
    directory = Path(classroom_directory).resolve()
    if (not isinstance(session_id, str) or not session_id or not isinstance(stage_id, str) or not stage_id
            or type(base_policy_version) is not int or base_policy_version < 1
            or not _is_sha(base_policy_sha256)):
        raise ValueError("follow-up discovery identity is invalid")
    if classroom is not None and (not isinstance(classroom, dict) or classroom.get("id") != stage_id):
        raise ValueError("follow-up courseware identity is invalid")
    if classroom is None and not _is_sha(candidate_source_sha256):
        raise ValueError("follow-up candidate source identity is missing")
    candidate, candidate_raw = _candidate_file(directory / stage_id / "textbook-authoring-candidate.json",
                                                directory, session_id, stage_id)
    contract = candidate.get("frozenContract")
    if (not isinstance(contract, dict) or not isinstance(contract.get("contract"), dict)
            or not _is_sha(contract.get("sha256"))
            or digest(contract["contract"]) != contract["sha256"]):
        raise ValueError("follow-up candidate contract is invalid")
    base_policy = contract["contract"].get("interactionPolicy")
    if (not isinstance(base_policy, dict) or not isinstance(base_policy.get("policy"), dict)
            or base_policy.get("sha256") != base_policy_sha256
            or digest(base_policy["policy"]) != base_policy_sha256
            or base_policy["policy"].get("version") != base_policy_version):
        raise ValueError("follow-up base policy differs from the frozen candidate")
    if classroom is not None:
        records, scenes = candidate.get("scenes"), classroom.get("scenes")
        if (not isinstance(records, list) or not isinstance(scenes, list) or len(records) != len(scenes)
                or any(not isinstance(record, dict) or not isinstance(scene, dict)
                       or not _scene_record_matches(record, scene)
                       for record, scene in zip(records, scenes))):
            raise ValueError("follow-up candidate no longer matches the reviewed courseware")
        candidate_source_sha256 = digest(classroom)

    evidence_root = directory.parent / "textbook-current-review-revisions"
    stage_root = evidence_root / hashlib.sha256(session_id.encode()).hexdigest() / stage_id
    if not stage_root.exists():
        return None
    if stage_root.is_symlink() or not stage_root.is_dir():
        raise ValueError("revision archive stage directory is invalid")
    folders = sorted(stage_root.iterdir())
    entries = [_revision_entry(folder, stage_root, session_id, stage_id, contract["sha256"])
               for folder in folders]
    current_file_sha = hashlib.sha256(candidate_raw).hexdigest()
    canonical_matches = [entry for entry in entries
                         if entry["plan"]["afterCandidateSha256"] == candidate["sha256"]]
    if any(entry["plan"]["afterCandidateFileSha256"] != current_file_sha for entry in canonical_matches):
        raise ValueError("current candidate bytes differ from its revision receipt")
    current = [entry for entry in canonical_matches
               if entry["plan"]["afterCandidateFileSha256"] == current_file_sha]
    if not current:
        return None
    if len(current) != 1:
        raise ValueError("multiple revision receipts claim the current candidate")

    by_after = {}
    for entry in entries:
        by_after.setdefault(entry["plan"]["afterCandidateSha256"], []).append(entry)
    chain, seen = [], set()
    entry = current[0]
    while entry is not None:
        revision_id = entry["plan"]["sha256"]
        if revision_id in seen:
            raise ValueError("revision chain contains a cycle")
        seen.add(revision_id)
        chain.append(entry)
        predecessors = by_after.get(entry["plan"]["beforeCandidateSha256"], [])
        if len(predecessors) > 1:
            raise ValueError("revision chain has an ambiguous predecessor")
        predecessor = predecessors[0] if predecessors else None
        if predecessor is not None and predecessor["plan"]["afterCandidateFileSha256"] != entry["plan"]["beforeCandidateFileSha256"]:
            raise ValueError("revision chain candidate bytes do not join")
        entry = predecessor
    chain.reverse()
    complete_ids = []
    for entry in chain:
        for scene_id in entry["completeSceneIds"]:
            if scene_id not in complete_ids:
                complete_ids.append(scene_id)
    if not complete_ids:
        return None

    snapshot = freeze_interaction_policy()
    current_policy = snapshot["policy"]
    quality_contract = current_policy.get("wholeCourseQualityContract")
    if current_policy.get("version", 0) < 2 or not isinstance(quality_contract, dict):
        raise ValueError("current policy does not define the whole-course quality contract")
    body = {
        "schemaVersion": SCHEMA, "status": STATUS, "verification": VERIFICATION,
        "sessionId": session_id, "stageId": stage_id,
        "baseInteractionPolicyVersion": base_policy_version,
        "baseInteractionPolicySha256": base_policy_sha256,
        "currentInteractionPolicyVersion": current_policy["version"],
        "currentInteractionPolicySha256": snapshot["sha256"],
        "wholeCourseQualityContractSha256": digest(quality_contract),
        "candidateSourceSha256": candidate_source_sha256, "candidateSha256": candidate["sha256"],
        "candidateFileSha256": current_file_sha,
        "revisionIds": [item["plan"]["sha256"] for item in chain],
        "revisionReceiptSha256s": [item["receipt"]["sha256"] for item in chain],
        "completeSceneIds": complete_ids,
    }
    value = {**body, "sha256": digest(body)}
    return validate_complete_scene_review_followup(value, candidate_source_sha256=candidate_source_sha256,
                                                    current_policy=snapshot)
