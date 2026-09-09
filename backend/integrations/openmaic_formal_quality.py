"""Bind independent teaching QA to the final classroom, not generation claims."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import re
from typing import Any, Mapping

from integrations.openmaic_formal_pedagogy import adaptive_policy, validate_generation_grade_boundary


QUALITY_DIMENSIONS = ["grade_fit", "goal_coverage", "teaching_sequence", "misconception_repair",
                      "meaningful_interaction", "assessment_alignment", "language_load"]
QUALITY_VIEWPORTS = [{"width": 1280, "height": 720}, {"width": 1024, "height": 768}]
_SPEECH_AUDIO_FIELDS = {"audioUrl", "audioSrc", "audio", "audioDuration", "duration", "ttsProvider", "ttsModel"}
_SHA = re.compile(r"[0-9a-f]{64}")
_ID = re.compile(r"[A-Za-z0-9_-]{1,255}")


def _js_number(value: int | float) -> str:
    """Use JSON.stringify's finite binary64 decimal/exponent presentation."""

    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite formal quality number")
    if number == 0:
        return "0"
    negative = number < 0
    token = repr(abs(number)).lower()
    coefficient, _, exponent = token.partition("e")
    whole, _, fraction = coefficient.partition(".")
    digits = (whole + fraction).lstrip("0")
    position = len(whole) + int(exponent or "0")
    if whole == "0":
        position -= len(whole + fraction) - len((whole + fraction).lstrip("0"))
    digits = digits.rstrip("0") or "0"
    if 1e-6 <= abs(number) < 1e21:
        if position <= 0:
            text = "0." + "0" * -position + digits
        elif position >= len(digits):
            text = digits + "0" * (position - len(digits))
        else:
            text = digits[:position] + "." + digits[position:]
    else:
        power = position - 1
        text = digits[0] + (("." + digits[1:]) if len(digits) > 1 else "")
        text += "e" + ("+" if power >= 0 else "-") + str(abs(power))
    return ("-" if negative else "") + text


def _utf16_key(value: str) -> bytes:
    return value.encode("utf-16-be", errors="surrogatepass")


def quality_canonical_json(value: object) -> str:
    """Match new Runtime qualityCanonical + JSON.stringify; never used by v1."""

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)):
        return _js_number(value)
    if isinstance(value, list):
        return "[" + ",".join(quality_canonical_json(item) for item in value) + "]"
    if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
        keys = sorted(value, key=_utf16_key)
        # ECMAScript enumerates canonical array-index property names first,
        # even when the object was constructed with lexically sorted keys.
        indexes = [key for key in keys if re.fullmatch(r"0|[1-9][0-9]*", key)
                   and len(key) <= 10 and int(key) < 2**32 - 1]
        keys = sorted(indexes, key=int) + [key for key in keys if key not in indexes]
        return "{" + ",".join(json.dumps(key, ensure_ascii=False) + ":" + quality_canonical_json(value[key])
                              for key in keys) + "}"
    raise ValueError("non-JSON formal quality value")


def quality_sha(value: object) -> str:
    return hashlib.sha256(quality_canonical_json(value).encode()).hexdigest()


def _digest(value: object) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _identifier(value: object) -> bool:
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _exact(value: object, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError("invalid formal teaching quality fields")
    return value


def quality_scene_projection(scene: object, index: int) -> dict[str, Any]:
    if (not isinstance(scene, Mapping) or not isinstance(scene.get("id"), str)
            or not isinstance(scene.get("type"), str) or not isinstance(scene.get("title"), str)
            or not isinstance(scene.get("actions"), list) or not isinstance(scene.get("content"), Mapping)):
        raise ValueError("invalid formal teaching quality scene")
    return {"id": scene["id"], "type": scene["type"], "title": scene["title"], "order": index,
        "content": deepcopy(dict(scene["content"])),
        "actions": [{key: deepcopy(value) for key, value in action.items() if key not in _SPEECH_AUDIO_FIELDS}
                    if isinstance(action, Mapping) and action.get("type") == "speech" else deepcopy(action)
                    for action in scene["actions"]]}


def quality_snapshot(classroom: Mapping[str, Any]) -> dict[str, Any]:
    stage, scenes = classroom.get("stage"), classroom.get("scenes")
    if (not isinstance(stage, Mapping) or not isinstance(stage.get("id"), str)
            or not isinstance(stage.get("name"), str) or not isinstance(scenes, list) or not 1 <= len(scenes) <= 60
            or any(not isinstance(scene, Mapping) or type(scene.get("order")) not in (int, float)
                   or not math.isfinite(scene["order"]) for scene in scenes)):
        raise ValueError("invalid formal teaching quality snapshot")
    projected = [quality_scene_projection(scene, index)
                 for index, scene in enumerate(sorted(scenes, key=lambda s: s["order"]))]
    if len({scene["id"] for scene in projected}) != len(projected):
        raise ValueError("duplicate formal teaching quality scene")
    return {"stage": {"id": stage["id"], "name": stage["name"]}, "scenes": projected}


def quality_scene_text(scene: Mapping[str, Any]) -> str:
    strings: list[str] = []
    def collect(value: object) -> None:
        if isinstance(value, str):
            strings.append(value)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, Mapping):
            for key in sorted(value, key=_utf16_key):
                collect(value[key])
    collect(scene["content"])
    collect(scene["actions"])
    return "\n".join(strings)


def _evidence(value: object, scene_ids: set[str]) -> None:
    if not isinstance(value, list) or not 1 <= len(value) <= 60:
        raise ValueError("formal teaching quality evidence is missing")
    for item in value:
        item = _exact(item, {"sceneId", "quote"})
        if (not isinstance(item["sceneId"], str) or item["sceneId"] not in scene_ids
                or not isinstance(item["quote"], str) or not item["quote"].strip()
                or not 3 <= len(item["quote"]) <= 1000):
            raise ValueError("invalid formal teaching quality citation")


def teaching_quality_receipt(value: object) -> dict[str, Any]:
    raw = _exact(value, {"schemaVersion", "policyId", "status", "sessionId", "stageId", "gradeBoundarySha256",
        "selectionPlanSha256", "teachingBriefSha256", "snapshotSha256", "sceneHashes", "renderChecks", "review", "receiptSha256"})
    if (raw["schemaVersion"] != "mira.openmaic.teaching-quality-receipt.v1"
            or raw["policyId"] != "mira-primary-quality.v1" or raw["status"] != "passed"
            or not _identifier(raw["sessionId"]) or not _identifier(raw["stageId"])
            or any(not _digest(raw[key]) for key in ("gradeBoundarySha256", "selectionPlanSha256",
                "teachingBriefSha256", "snapshotSha256", "receiptSha256"))):
        raise ValueError("invalid formal teaching quality identity")
    scene_hashes = raw["sceneHashes"]
    if not isinstance(scene_hashes, list) or not 1 <= len(scene_hashes) <= 60:
        raise ValueError("formal teaching quality scene hashes are missing")
    scene_ids: set[str] = set()
    for row in scene_hashes:
        row = _exact(row, {"sceneId", "sceneSha256"})
        if not _identifier(row["sceneId"]) or not _digest(row["sceneSha256"]) or row["sceneId"] in scene_ids:
            raise ValueError("invalid formal teaching quality scene hash")
        scene_ids.add(row["sceneId"])
    checks = raw["renderChecks"]
    if not isinstance(checks, list) or len(checks) != len(scene_hashes) * len(QUALITY_VIEWPORTS):
        raise ValueError("formal teaching quality render coverage is incomplete")
    for index, check in enumerate(checks):
        check = _exact(check, {"sceneId", "sceneSha256", "viewport", "screenshotSha256", "domSha256", "passed", "probeCount"})
        scene_hash = scene_hashes[index // len(QUALITY_VIEWPORTS)]
        if (check["sceneId"] != scene_hash["sceneId"] or check["sceneSha256"] != scene_hash["sceneSha256"]
                or quality_sha(check["viewport"]) != quality_sha(QUALITY_VIEWPORTS[index % len(QUALITY_VIEWPORTS)])
                or not _digest(check["screenshotSha256"]) or not _digest(check["domSha256"])
                or check["passed"] is not True or type(check["probeCount"]) is not int or not 0 <= check["probeCount"] <= 10000):
            raise ValueError("invalid formal teaching quality render result")
    review = _exact(raw["review"], {"providerId", "modelId", "requestIdHash", "inputSha256", "dimensions", "objectives"})
    expected_input = {key: raw[key] for key in ("snapshotSha256", "gradeBoundarySha256", "selectionPlanSha256",
                                               "teachingBriefSha256", "renderChecks")}
    if (review["providerId"] != "deepseek" or review["modelId"] != "deepseek-v4-flash"
            or not _digest(review["requestIdHash"]) or review["inputSha256"] != quality_sha(expected_input)):
        raise ValueError("formal teaching quality review identity drifted")
    dimensions = review["dimensions"]
    if not isinstance(dimensions, list) or len(dimensions) != len(QUALITY_DIMENSIONS):
        raise ValueError("formal teaching quality dimensions are incomplete")
    seen_dimensions: set[str] = set()
    for dimension in dimensions:
        dimension = _exact(dimension, {"id", "passed", "evidence"})
        if (not isinstance(dimension["id"], str) or dimension["id"] not in QUALITY_DIMENSIONS
                or dimension["id"] in seen_dimensions or dimension["passed"] is not True):
            raise ValueError("formal teaching quality dimension failed")
        seen_dimensions.add(dimension["id"])
        _evidence(dimension["evidence"], scene_ids)
    objectives = review["objectives"]
    if not isinstance(objectives, list) or not 1 <= len(objectives) <= 50:
        raise ValueError("formal teaching quality objectives are missing")
    seen_objectives: set[int] = set()
    for objective in objectives:
        objective = _exact(objective, {"objectiveIndex", "evidence"})
        if (type(objective["objectiveIndex"]) is not int or not 0 <= objective["objectiveIndex"] < 50
                or objective["objectiveIndex"] in seen_objectives):
            raise ValueError("invalid formal teaching quality objective")
        seen_objectives.add(objective["objectiveIndex"])
        _evidence(objective["evidence"], scene_ids)
    unsigned = dict(raw)
    digest = unsigned.pop("receiptSha256")
    if digest != quality_sha(unsigned):
        raise ValueError("formal teaching quality receipt hash mismatch")
    return deepcopy(dict(raw))


def professional_quality_fields(professional: Mapping[str, Any]) -> dict[str, Any]:
    if "teachingQuality" not in professional:
        return {}
    return {"teachingQuality": teaching_quality_receipt(professional["teachingQuality"])}


def _bound_quality(professional: Mapping[str, Any], generation: Mapping[str, Any]) -> dict[str, Any] | None:
    adaptive = adaptive_policy(generation.get("professionalCreationPolicy"))
    if adaptive != ("teachingQuality" in professional):
        raise ValueError("formal teaching quality policy and receipt mismatch")
    if not adaptive:
        return None
    validate_generation_grade_boundary(generation)
    receipt = teaching_quality_receipt(professional["teachingQuality"])
    unsigned = dict(professional)
    parent_hash = unsigned.pop("receiptSha256", None)
    skill = professional.get("skillOrchestration")
    plan = skill.get("selectionPlan") if isinstance(skill, Mapping) else None
    if (not _digest(parent_hash) or quality_sha(unsigned) != parent_hash or not isinstance(plan, Mapping)
            or receipt["sessionId"] != professional.get("sessionId")
            or receipt["stageId"] != professional.get("classroomId")
            or receipt["teachingBriefSha256"] != professional.get("teachingBriefSha256")
            or receipt["teachingBriefSha256"] != generation.get("teachingBriefSha256")
            or receipt["gradeBoundarySha256"] != generation.get("gradeBoundarySha256")
            or receipt["selectionPlanSha256"] != plan.get("planSha256")):
        raise ValueError("formal teaching quality authority drifted")
    count = len(generation["gradeBoundary"]["learningObjectives"])
    if {item["objectiveIndex"] for item in receipt["review"]["objectives"]} != set(range(count)):
        raise ValueError("formal teaching quality omitted a locked objective")
    return receipt


def validate_classroom_quality(professional: Mapping[str, Any], generation: Mapping[str, Any],
                               classroom: Mapping[str, Any]) -> dict[str, Any] | None:
    receipt = _bound_quality(professional, generation)
    if receipt is None:
        return None
    snapshot = quality_snapshot(classroom)
    hashes = [{"sceneId": scene["id"], "sceneSha256": quality_sha(scene)} for scene in snapshot["scenes"]]
    if (snapshot["stage"]["id"] != receipt["stageId"] or quality_sha(snapshot) != receipt["snapshotSha256"]
            or hashes != receipt["sceneHashes"]):
        raise ValueError("formal teaching quality does not match the final classroom")
    texts = {scene["id"]: quality_scene_text(scene) for scene in snapshot["scenes"]}
    for row in [*receipt["review"]["dimensions"], *receipt["review"]["objectives"]]:
        if any(evidence["quote"] not in texts[evidence["sceneId"]] for evidence in row["evidence"]):
            raise ValueError("formal teaching quality quote is not in the classroom")
    interactive = {scene["id"] for scene in snapshot["scenes"] if scene["type"] == "interactive"}
    if any(check["sceneId"] in interactive and check["probeCount"] < 1 for check in receipt["renderChecks"]):
        raise ValueError("formal teaching quality did not exercise the interaction")
    return {"verified": True, "snapshotSha256": receipt["snapshotSha256"],
            "sceneHashes": deepcopy(hashes), "receiptSha256": receipt["receiptSha256"]}


def validate_quality_manifest(manifest: Mapping[str, Any]) -> None:
    professional, generation = manifest.get("professionalCreation"), manifest.get("generationContract")
    if not isinstance(professional, Mapping) or not isinstance(generation, Mapping):
        raise ValueError("formal teaching quality authority is missing")
    receipt = _bound_quality(professional, generation)
    evidence = manifest.get("formalEvidence")
    if receipt is None:
        if isinstance(evidence, Mapping) and "teachingQuality" in evidence:
            raise ValueError("historical manifest contains new teaching quality evidence")
        return
    professional_evidence = evidence.get("professionalCreation") if isinstance(evidence, Mapping) else None
    authority = evidence.get("runtimeEventAuthority") if isinstance(evidence, Mapping) else None
    scenes = authority.get("scenes") if isinstance(authority, Mapping) else None
    if (not isinstance(professional_evidence, Mapping) or professional_evidence.get("verified") is not True
            or professional_evidence.get("receiptSha256") != professional.get("receiptSha256")
            or professional_evidence.get("teachingQuality") != receipt
            or evidence.get("teachingQuality") != {"verified": True, "snapshotSha256": receipt["snapshotSha256"],
                "sceneHashes": receipt["sceneHashes"], "receiptSha256": receipt["receiptSha256"]}
            or not isinstance(scenes, list) or len(scenes) != len(receipt["sceneHashes"])
            or any(not isinstance(scene, Mapping) for scene in scenes)
            or [scene.get("sceneId") for scene in scenes] != [item["sceneId"] for item in receipt["sceneHashes"]]
            or type(manifest.get("sceneCount")) is not int or manifest["sceneCount"] != len(scenes)):
        raise ValueError("formal teaching quality manifest evidence mismatch")
    skill = professional.get("skillOrchestration")
    contexts = skill.get("sceneContexts") if isinstance(skill, Mapping) else None
    if not isinstance(contexts, list) or any(not isinstance(context, Mapping) for context in contexts):
        raise ValueError("formal teaching quality scene types are missing")
    interactive = {context.get("sceneId") for context in contexts if context.get("sceneType") == "interactive"}
    if any(check["sceneId"] in interactive and check["probeCount"] < 1 for check in receipt["renderChecks"]):
        raise ValueError("formal teaching quality interaction evidence is missing")
