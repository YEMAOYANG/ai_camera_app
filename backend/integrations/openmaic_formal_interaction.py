"""Frozen primary interaction design and final-artifact evidence.

This receipt proves that production QA exercised a teaching operation. A child's
own operation is recorded separately by the authenticated classroom event path.
"""
from __future__ import annotations

from copy import deepcopy
from html.parser import HTMLParser
import json
import re
from typing import Any, Mapping

from integrations.openmaic_formal_quality import (
    QUALITY_VIEWPORTS, quality_sha, quality_snapshot, quality_scene_text,
    teaching_quality_receipt,
)

INTERACTION_DESIGN_POLICY = {
    "schemaVersion": "mira.openmaic.interaction-design.v1",
    "policyId": "mira-primary-adaptive-interaction.v1",
    "enabled": True,
    "profile": "primary-adaptive",
    "objectiveCoverageRequired": True,
    "demonstrationRequired": True,
    "learnerOperationRequired": True,
    "explanatoryFeedbackRequired": True,
    "independentJudgmentRequired": True,
    "finalSnapshotRequired": True,
    "renderedInteractionRequired": True,
}
from integrations.openmaic_formal_exploration import EXPLORATION_POLICY, validate_exploration, validate_exploration_checks
from integrations.openmaic_formal_visual import VISUAL_RUBRIC_VERSION, visual_review_receipt
MULTISTATE_INTERACTION_POLICY = {**deepcopy(INTERACTION_DESIGN_POLICY),
    "schemaVersion": "mira.openmaic.interaction-design.v2", "policyId": "mira-primary-multistate-interaction.v2",
    "explorationPolicy": EXPLORATION_POLICY, "visualRubricVersion": VISUAL_RUBRIC_VERSION, "visualReviewRequired": True}
PLAN_SCHEMA = "mira.openmaic.interaction-design-plan.v1"
RECEIPT_SCHEMA = "mira.openmaic.interaction-design-receipt.v1"
_ID = re.compile(r"[A-Za-z0-9_-]{1,255}")
_SHA = re.compile(r"[0-9a-f]{64}")
_SELECTOR = re.compile(r"#[A-Za-z][A-Za-z0-9_-]{0,98}")


def _exact(value: object, fields: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("invalid formal interaction fields")
    return value


def _identifier(value: object) -> bool:
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _digest(value: object) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _text(value: object, maximum: int = 500) -> bool:
    return isinstance(value, str) and 3 <= len(value.strip()) and len(value) <= maximum


def _observed_assessment(value: object) -> Mapping[str, Any]:
    row = _exact(value, {"schemaVersion", "criteria"})
    if (row["schemaVersion"] != "mira.learning.observed-assessment.v1"
            or not isinstance(row["criteria"], list) or not 1 <= len(row["criteria"]) <= 30
            or any(not _text(item, 16000) for item in row["criteria"])):
        raise ValueError("invalid observed assessment criteria")
    return row


def _objective(value: object, *, checks: bool, multistate: bool = False,
               observed: Mapping[str, Any] | None = None) -> None:
    row = _exact(value, {"objectiveIndex", "demonstration", "operation", "feedback", "independentJudgment"}
                 | ({"checks"} if checks else set()) | ({"exploration"} if multistate else set()))
    if type(row["objectiveIndex"]) is not int or not 0 <= row["objectiveIndex"] < 50:
        raise ValueError("invalid interaction objective index")
    demonstration = _exact(row["demonstration"], {"sceneId", "quote"})
    if not _identifier(demonstration["sceneId"]) or not _text(demonstration["quote"]):
        raise ValueError("interaction demonstration is missing")
    operation = row["operation"]
    operation = _exact(operation, {"sceneId", "controlSelector", "action"}
                       | ({"value"} if isinstance(operation, Mapping) and "value" in operation else set()))
    if (not _identifier(operation["sceneId"]) or not isinstance(operation["controlSelector"], str)
            or not _SELECTOR.fullmatch(operation["controlSelector"])
            or operation["action"] not in ("click", "fill", "range", "select")
            or ("value" in operation and (not isinstance(operation["value"], str)
                                         or not operation["value"].strip() or len(operation["value"]) > 500))
            or (operation["action"] != "click" and "value" not in operation)):
        raise ValueError("invalid teaching operation")
    feedback = _exact(row["feedback"], {"sceneId", "selector", "textIncludes", "reasonQuote"})
    if (feedback["sceneId"] != operation["sceneId"] or not isinstance(feedback["selector"], str)
            or not _SELECTOR.fullmatch(feedback["selector"])
            or feedback["selector"] == operation["controlSelector"]
            or not _text(feedback["textIncludes"]) or not _text(feedback["reasonQuote"])):
        raise ValueError("interaction requires independent explanatory feedback")
    judgment = _exact(row["independentJudgment"], {"sceneId", "observationIndex", "criterionText", "confirmationAuthority"}
                      if observed is not None else {"sceneId", "questionId"})
    if not _identifier(judgment["sceneId"]):
        raise ValueError("interaction independent judgment is missing")
    if observed is not None:
        if (type(judgment["observationIndex"]) is not int
                or not 0 <= judgment["observationIndex"] < len(observed["criteria"])
                or judgment["criterionText"] != observed["criteria"][judgment["observationIndex"]]
                or judgment["confirmationAuthority"] != "parent_or_teacher"):
            raise ValueError("interaction observation must use an exact authorized criterion")
    elif not _identifier(judgment["questionId"]):
        raise ValueError("interaction independent judgment is missing")
    if multistate:
        validate_exploration(row["exploration"])
    if not checks:
        return
    if not isinstance(row["checks"], list) or len(row["checks"]) != len(QUALITY_VIEWPORTS):
        raise ValueError("interaction viewport coverage is incomplete")
    for index, check in enumerate(row["checks"]):
        check = _exact(check, {"viewport", "sceneSha256", "screenshotSha256", "domSha256", "probeId"})
        if (quality_sha(check["viewport"]) != quality_sha(QUALITY_VIEWPORTS[index])
                or any(not _digest(check[key]) for key in ("sceneSha256", "screenshotSha256", "domSha256"))
                or check["probeId"] != f"objective-{row['objectiveIndex']}"):
            raise ValueError("invalid interaction render probe")


def interaction_design_receipt(value: object) -> dict[str, Any]:
    multistate = isinstance(value, Mapping) and value.get("schemaVersion") == "mira.openmaic.interaction-design-receipt.v2"
    observed = _observed_assessment(value["observedAssessment"]) if isinstance(value, Mapping) and "observedAssessment" in value else None
    row = _exact(value, {"schemaVersion", "policyId", "status", "sessionId", "stageId", "gradeBoundarySha256",
                         "snapshotSha256", "planSha256", "teachingQualityReceiptSha256", "objectives", "receiptSha256"} | ({"visualReview", "explorationChecks"} if multistate else set()) | ({"observedAssessment"} if observed is not None else set()))
    if (row["schemaVersion"] != ("mira.openmaic.interaction-design-receipt.v2" if multistate else RECEIPT_SCHEMA) or row["policyId"] != (MULTISTATE_INTERACTION_POLICY if multistate else INTERACTION_DESIGN_POLICY)["policyId"]
            or row["status"] != "passed" or not _identifier(row["sessionId"]) or not _identifier(row["stageId"])
            or any(not _digest(row[key]) for key in ("gradeBoundarySha256", "snapshotSha256", "planSha256",
                                                     "teachingQualityReceiptSha256", "receiptSha256"))):
        raise ValueError("invalid interaction receipt identity")
    objectives = row["objectives"]
    if not isinstance(objectives, list) or not 1 <= len(objectives) <= 30:
        raise ValueError("interaction objectives are missing")
    for objective in objectives:
        _objective(objective, checks=True, multistate=multistate, observed=observed)
    if {item["objectiveIndex"] for item in objectives} != set(range(len(objectives))):
        raise ValueError("interaction objective coverage is incomplete")
    if multistate:
        validate_exploration_checks(row, QUALITY_VIEWPORTS)
    plan = {"schemaVersion": "mira.openmaic.interaction-design-plan.v2" if multistate else PLAN_SCHEMA,
            "objectives": [{key: value for key, value in item.items() if key != "checks"} for item in objectives],
            **({"observedAssessment": observed} if observed is not None else {})}
    unsigned = dict(row)
    digest = unsigned.pop("receiptSha256")
    if row["planSha256"] != quality_sha(plan) or digest != quality_sha(unsigned):
        raise ValueError("interaction receipt digest mismatch")
    return deepcopy(dict(row))


def professional_interaction_fields(professional: Mapping[str, Any]) -> dict[str, Any]:
    if "interactionDesign" not in professional:
        return {}
    return {"interactionDesign": interaction_design_receipt(professional["interactionDesign"])}


def _bound_interaction(professional: Mapping[str, Any], generation: Mapping[str, Any]) -> dict[str, Any] | None:
    policy = generation.get("professionalCreationPolicy")
    selected = policy.get("interactionDesignPolicy") if isinstance(policy, Mapping) else None
    if selected is None:
        if "interactionDesign" in professional:
            raise ValueError("historical policy cannot acquire interaction evidence")
        return None
    if quality_sha(selected) not in {quality_sha(INTERACTION_DESIGN_POLICY), quality_sha(MULTISTATE_INTERACTION_POLICY)}:
        raise ValueError("unsupported interaction design policy")
    receipt = interaction_design_receipt(professional.get("interactionDesign"))
    quality = teaching_quality_receipt(professional.get("teachingQuality"), generation_contract=generation)
    if receipt["policyId"] != selected["policyId"]:
        raise ValueError("interaction policy and receipt version mismatch")
    if receipt["schemaVersion"].endswith(".v2"):
        visual_review_receipt(receipt["visualReview"], quality, generation_contract=generation)
        for item in receipt["objectives"]:
            validate_exploration(item["exploration"], skill_id=generation.get("gradeBoundary", {}).get("skillId"))
    unsigned = dict(professional)
    digest = unsigned.pop("receiptSha256", None)
    if (digest != quality_sha(unsigned) or receipt["sessionId"] != professional.get("sessionId")
            or receipt["stageId"] != professional.get("classroomId")
            or receipt["gradeBoundarySha256"] != generation.get("gradeBoundarySha256")
            or receipt["snapshotSha256"] != quality["snapshotSha256"]
            or receipt["teachingQualityReceiptSha256"] != quality["receiptSha256"]):
        raise ValueError("interaction receipt authority mismatch")
    boundary = generation.get("gradeBoundary")
    objectives = boundary.get("learningObjectives") if isinstance(boundary, Mapping) else None
    if not isinstance(objectives, list) or len(receipt["objectives"]) != len(objectives):
        raise ValueError("interaction omitted a locked teaching objective")
    brief = generation.get("teachingBrief")
    lesson = brief.get("lesson") if isinstance(brief, Mapping) else None
    flow = lesson.get("teachingFlow") if isinstance(lesson, Mapping) else None
    independent = flow.get("independentQuestionIds") if isinstance(flow, Mapping) else None
    observed = receipt.get("observedAssessment")
    observed_lesson = (isinstance(brief, Mapping) and brief.get("schemaVersion") == "mira.learning.formal-runtime-teaching-brief.progressive.v1"
                       and isinstance(lesson, Mapping) and lesson.get("assessmentMode") == "observed")
    if observed_lesson:
        observations = flow.get("observations") if isinstance(flow, Mapping) else None
        if (not isinstance(observations, list) or any(not isinstance(item, Mapping) for item in observations)
                or observed != {"schemaVersion": "mira.learning.observed-assessment.v1", "criteria": [item.get("text") for item in observations]}
                or independent != [] or lesson.get("questions") != []
                or lesson.get("autoMasteryEligible") is not False or lesson.get("manualConfirmationRequired") is not True):
            raise ValueError("interaction observation authority differs from the frozen lesson")
    elif observed is not None or not isinstance(independent, list) or any(item["independentJudgment"].get("questionId") not in independent
                                                                         for item in receipt["objectives"]):
        raise ValueError("interaction judgment must use a locked independent assessment")
    hashes = {item["sceneId"]: item["sceneSha256"] for item in quality["sceneHashes"]}
    for item in receipt["objectives"]:
        if any(item[part]["sceneId"] not in hashes for part in ("demonstration", "operation", "feedback", "independentJudgment")):
            raise ValueError("interaction references an unknown scene")
        if any(check["sceneSha256"] != hashes[item["operation"]["sceneId"]] for check in item["checks"]):
            raise ValueError("interaction probe references a different scene version")
        if observed is not None:
            for viewport in QUALITY_VIEWPORTS:
                if not any(check["sceneId"] == item["independentJudgment"]["sceneId"]
                           and quality_sha(check["viewport"]) == quality_sha(viewport)
                           and check["passed"] is True
                           and check["sceneSha256"] == hashes[item["independentJudgment"]["sceneId"]]
                           for check in quality["renderChecks"]):
                    raise ValueError("independent observation scene lacks final rendered evidence")
        for check in item["checks"]:
            if not any(observation["sceneId"] == item["operation"]["sceneId"]
                       and all(quality_sha(observation[key]) == quality_sha(check[key]) for key in
                               ("viewport", "sceneSha256", "screenshotSha256", "domSha256"))
                       and observation["passed"] is True and observation["probeCount"] >= 1
                       for observation in quality["renderChecks"]):
                raise ValueError("interaction render evidence is not bound to the final quality receipt")
    return receipt


class _PlanParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.active = False
        self.count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" and dict(attrs).get("id") == "mira-interaction-plan":
            if dict(attrs).get("type") != "application/json":
                raise ValueError("interaction plan must be JSON data")
            self.active = True
            self.count += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.active = False

    def handle_data(self, data: str) -> None:
        if self.active:
            self.parts.append(data)


def _evidence(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {"verified": True, "snapshotSha256": receipt["snapshotSha256"],
            "planSha256": receipt["planSha256"], "receiptSha256": receipt["receiptSha256"],
            "objectiveCount": len(receipt["objectives"])}


def validate_classroom_interaction(professional: Mapping[str, Any], generation: Mapping[str, Any],
                                   classroom: Mapping[str, Any]) -> dict[str, Any] | None:
    receipt = _bound_interaction(professional, generation)
    if receipt is None:
        return None
    snapshot = quality_snapshot(classroom)
    if quality_sha(snapshot) != receipt["snapshotSha256"]:
        raise ValueError("interaction does not match the final classroom")
    scenes = {scene["id"]: scene for scene in snapshot["scenes"]}
    parser = _PlanParser()
    first_interactive = next((scene["id"] for scene in snapshot["scenes"] if scene["type"] == "interactive"), None)
    for scene in snapshot["scenes"]:
        if scene["type"] == "interactive":
            html = scene["content"].get("html")
            if isinstance(html, str):
                before = parser.count
                parser.feed(html)
                if parser.count > before and scene["id"] != first_interactive:
                    raise ValueError("interaction plan must be in the first interactive scene")
    if parser.count != 1 or len("".join(parser.parts)) > 40000:
        raise ValueError("classroom requires exactly one interaction plan")
    try:
        plan = json.loads("".join(parser.parts))
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid classroom interaction plan") from exc
    if quality_sha(plan) != receipt["planSha256"]:
        raise ValueError("interaction plan drifted after validation")
    for item in receipt["objectives"]:
        demo = item["demonstration"]
        operation = scenes[item["operation"]["sceneId"]]
        judgment = scenes[item["independentJudgment"]["sceneId"]]
        demo_scene = scenes[demo["sceneId"]]
        if receipt.get("observedAssessment") is not None:
            judgment_valid = (judgment["type"] in {"slide", "interactive"}
                and item["independentJudgment"]["criterionText"] in quality_scene_text(judgment))
        else:
            judgment_valid = (judgment["type"] == "quiz" and item["independentJudgment"]["questionId"] in
                              [q.get("id") for q in judgment["content"].get("questions", [])])
        if (not any(action.get("type") == "speech" and demo["quote"] in str(action.get("text", ""))
                    for action in demo_scene["actions"] if isinstance(action, Mapping))
                or operation["type"] != "interactive" or not judgment_valid
                or demo_scene["order"] > operation["order"] or judgment["order"] <= operation["order"]
                or item["feedback"]["reasonQuote"] not in quality_scene_text(operation)):
            raise ValueError("interaction teaching chain is not grounded in the classroom")
    return _evidence(receipt)


def validate_interaction_manifest(manifest: Mapping[str, Any]) -> None:
    professional, generation = manifest.get("professionalCreation"), manifest.get("generationContract")
    if not isinstance(professional, Mapping) or not isinstance(generation, Mapping):
        raise ValueError("interaction manifest authority is missing")
    receipt = _bound_interaction(professional, generation)
    evidence = manifest.get("formalEvidence")
    if receipt is None:
        if isinstance(evidence, Mapping) and "interactionDesign" in evidence:
            raise ValueError("historical manifest contains interaction evidence")
        return
    parent = evidence.get("professionalCreation") if isinstance(evidence, Mapping) else None
    if (not isinstance(parent, Mapping) or parent.get("interactionDesign") != receipt
            or parent.get("verified") is not True or parent.get("receiptSha256") != professional.get("receiptSha256")
            or evidence.get("interactionDesign") != _evidence(receipt)):
        raise ValueError("interaction manifest evidence mismatch")
    actions = evidence.get("requiredTeachingActions")
    if (not isinstance(actions, list) or len(actions) != int(evidence.get("discussionActionCount") or 0)
            or any(not isinstance(item, Mapping) or set(item) != {"sceneId", "actionId"}
                   or not _identifier(item["sceneId"]) or not _identifier(item["actionId"]) for item in actions)
            or len({(item["sceneId"], item["actionId"]) for item in actions}) != len(actions)):
        raise ValueError("required teaching action authority is missing")
