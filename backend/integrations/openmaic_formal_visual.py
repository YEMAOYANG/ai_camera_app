"""Actual image-review evidence, bound to the final immutable teaching artifact."""
from __future__ import annotations

from copy import deepcopy
from typing import Mapping
from integrations.openmaic_formal_quality import quality_sha

VISUAL_RUBRIC_VERSION = "mira.primary-teaching-visual.v1"
DIMENSIONS = ("legibility", "layout", "teachingGraphic", "interactionAffordance")


def visual_review_receipt(value, quality):
    expected = {"schemaVersion", "reviewerKind", "status", "rubricVersion", "snapshotSha256",
        "teachingQualityContextSha256", "sceneReviews", "providerId", "modelId", "providerRequestIdHash", "receiptSha256"}
    if not isinstance(value, Mapping) or set(value) not in (expected, expected | {"providerResponseModelId"}):
        raise ValueError("visual review receipt fields are invalid")
    if "providerResponseModelId" in value and (not isinstance(value["providerResponseModelId"], str) or not value["providerResponseModelId"].strip() or len(value["providerResponseModelId"]) > 200):
        raise ValueError("invalid visual provider response model identity")
    context = {key: quality[key] for key in ("snapshotSha256", "gradeBoundarySha256", "selectionPlanSha256", "teachingBriefSha256")}
    if (value["schemaVersion"] != "mira.openmaic.visual-review.v1" or value["reviewerKind"] != "vision_model"
        or value["status"] != "passed" or value["rubricVersion"] != VISUAL_RUBRIC_VERSION
        or value["snapshotSha256"] != quality["snapshotSha256"]
        or value["teachingQualityContextSha256"] != quality_sha(context)
        or value["providerId"] != "deepseek" or value["modelId"] != "deepseek-v4-flash-vision-exp"):
        raise ValueError("final artifact has not passed the configured visual model")
    reviews = value["sceneReviews"]
    observations = quality["renderChecks"]
    if not isinstance(reviews, list) or len(reviews) != len(observations):
        raise ValueError("visual review omitted a scene or viewport")
    seen = set()
    for row in reviews:
        if not isinstance(row, Mapping) or set(row) != {"sceneId", "sceneSha256", "viewport", "screenshotSha256", *DIMENSIONS, "notes"}:
            raise ValueError("invalid visual scene review")
        identity = quality_sha({"sceneId": row["sceneId"], "viewport": row["viewport"]})
        if (identity in seen or any(row[key] != "passed" for key in DIMENSIONS)
            or not isinstance(row["notes"], str) or not row["notes"].strip() or len(row["notes"]) > 2000
            or not any(all(quality_sha(o[key]) == quality_sha(row[key]) for key in
                          ("sceneId", "sceneSha256", "viewport", "screenshotSha256")) for o in observations)):
            raise ValueError("visual scene review does not match actual rendered evidence")
        seen.add(identity)
    import re
    if (not re.fullmatch("[a-f0-9]{64}", str(value["providerRequestIdHash"]))
        or value["receiptSha256"] != quality_sha({k: v for k, v in value.items() if k != "receiptSha256"})):
        raise ValueError("visual receipt digest mismatch")
    return deepcopy(dict(value))


def validate_visual_review(manifest):
    from integrations.openmaic_formal_interaction import _bound_interaction
    professional, generation = manifest["professionalCreation"], manifest["generationContract"]
    receipt = _bound_interaction(professional, generation)
    if receipt is None or receipt["schemaVersion"] == "mira.openmaic.interaction-design-receipt.v1":
        return None
    return visual_review_receipt(receipt["visualReview"], professional["teachingQuality"])
