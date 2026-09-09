"""Versioned professional image policy and immutable media receipt checks.

Keep the legacy policy exact: adding image generation must not change an
already-dispatched request's canonical body or a published receipt hash.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
import re
from typing import Any, Callable, Mapping

from integrations.openmaic_formal_skills import (
    FORMAL_SKILL_ORCHESTRATION_POLICY, ADAPTIVE_SKILL_ORCHESTRATION_POLICY,
    validate_skill_manifest,
)
from integrations.openmaic_formal_pedagogy import FORMAL_TEACHING_QUALITY_POLICY, validate_generation_grade_boundary
from integrations.openmaic_formal_quality import validate_quality_manifest
from integrations.openmaic_formal_video import FORMAL_VIDEO_POLICY, validate_video_manifest


FORMAL_IMAGE_POLICY = {
    "schemaVersion": "mira.openmaic.formal-image-policy.v1",
    "policyId": "mira-formal-qwen-image.v1",
    "enabled": True,
    "providerManaged": True,
    "providerId": "qwen-image",
    "modelId": "qwen-image-max",
    "usage": "teaching_need",
    "assetValidationRequired": True,
}
LEGACY_PROFESSIONAL_POLICY = {
    "schemaVersion": "mira.openmaic.professional-creation.v1",
    "mode": "professional_skill",
    "workflowVersion": "openmaic-pro-agent.v1",
    "skillId": "mira-primary-courseware",
    "supportingSkillIds": ["k12-core-literacy-planning", "deep-interactive"],
    "userPromptRequired": False,
    "webSearch": {
        "enabled": True,
        "providerManaged": True,
        "maxCalls": 4,
        "citationsRequired": True,
        "primarySourcesPreferred": True,
        "minimumFetchedSources": 1,
    },
    "studentToolsEnabled": False,
}
IMAGE_PROFESSIONAL_POLICY = {**deepcopy(LEGACY_PROFESSIONAL_POLICY), "image": FORMAL_IMAGE_POLICY}
INTEGRATED_PROFESSIONAL_POLICY = {
    **deepcopy(IMAGE_PROFESSIONAL_POLICY),
    "skillOrchestration": FORMAL_SKILL_ORCHESTRATION_POLICY,
}
PROFESSIONAL_POLICY = {
    **deepcopy(IMAGE_PROFESSIONAL_POLICY),
    "skillOrchestration": ADAPTIVE_SKILL_ORCHESTRATION_POLICY,
    "teachingQuality": FORMAL_TEACHING_QUALITY_POLICY,
}
# Freeze the adaptive image-only policy above: old request/receipt hashes stay exact.
VIDEO_PROFESSIONAL_POLICY = {**deepcopy(PROFESSIONAL_POLICY), "video": FORMAL_VIDEO_POLICY}
LEGACY_CONTENT_PROVIDER_PROFILE = "mira.learning.question-provider-profile.v105-deepseek-professional"
VIDEO_CONTENT_PROVIDER_PROFILE = "mira.learning.question-provider-profile.v106-deepseek-professional-video"
LEGACY_GENERATION_OPTIONS = {
    "mode": "professional_skill",
    "workflowVersion": "openmaic-pro-agent.v1",
    "skillId": "mira-primary-courseware",
    "supportingSkillIds": ["k12-core-literacy-planning", "deep-interactive"],
    "userPromptRequired": False,
    "enableWebSearch": True,
    "webSearchRequired": True,
    "enableImageGeneration": False,
    "enableVideoGeneration": False,
    "enableTTS": False,
    "agentMode": "generate",
    "providerInvocation": "openmaic_agent_managed",
    "automaticRetries": 0,
    "maximumAttempts": 1,
}
MEDIA_RECEIPT_SCHEMA = "mira.openmaic.formal-media-receipt.v1"
_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,255}")
_SHA = re.compile(r"[0-9a-f]{64}")
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def professional_policy(value: object) -> dict[str, Any]:
    # Canonical JSON comparisons also reject bool/int substitutions.
    if not isinstance(value, Mapping) or canonical_sha256(value) not in {
        canonical_sha256(LEGACY_PROFESSIONAL_POLICY), canonical_sha256(IMAGE_PROFESSIONAL_POLICY),
        canonical_sha256(INTEGRATED_PROFESSIONAL_POLICY), canonical_sha256(PROFESSIONAL_POLICY),
        canonical_sha256(VIDEO_PROFESSIONAL_POLICY)
    }:
        raise ValueError("unsupported formal professional policy")
    return deepcopy(dict(value))


def generation_options(value: object) -> dict[str, Any]:
    policy = professional_policy(value)
    return {**deepcopy(LEGACY_GENERATION_OPTIONS), "enableImageGeneration": "image" in policy,
            "enableVideoGeneration": "video" in policy}


def policy_from_target(target: object) -> dict[str, Any]:
    if not isinstance(target, Mapping):
        raise ValueError("formal target is missing")
    runtime = target.get("formalRuntimePolicy")
    if not isinstance(runtime, Mapping):
        raise ValueError("formal target runtime policy is missing")
    return professional_policy(runtime.get("professionalCreationPolicy"))


def compatible_preparation_targets(current: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Enumerate frozen contracts; never replace a persisted target in place."""
    policy_from_target(current)
    targets = [deepcopy(dict(current))]
    for historical_policy in (LEGACY_PROFESSIONAL_POLICY, IMAGE_PROFESSIONAL_POLICY,
                              INTEGRATED_PROFESSIONAL_POLICY, PROFESSIONAL_POLICY):
        historical = deepcopy(dict(current))
        historical["formalRuntimePolicy"]["professionalCreationPolicy"] = deepcopy(historical_policy)
        if "video" in policy_from_target(current):
            historical["contentProviderProfileContractVersion"] = LEGACY_CONTENT_PROVIDER_PROFILE
        if canonical_sha256(historical) not in {canonical_sha256(t) for t in targets}:
            targets.append(historical)
    return tuple(targets)


def compatible_preparation_target(persisted: object, current: object) -> bool:
    """Accept the exact historical policies without relaxing other target fields."""
    try:
        policy_from_target(persisted)
        return canonical_sha256(persisted) in {
            canonical_sha256(target) for target in compatible_preparation_targets(current)
        }
    except (TypeError, ValueError, KeyError):
        return False


def professional_image_fields(receipt: Mapping[str, Any]) -> dict[str, Any]:
    fields = {key: receipt[key] for key in ("imageGenerationEnabled", "imagePolicyId") if key in receipt}
    if fields and fields != {"imageGenerationEnabled": True, "imagePolicyId": FORMAL_IMAGE_POLICY["policyId"]}:
        raise ValueError("invalid professional image receipt policy")
    if fields and fields.get("imageGenerationEnabled") is not True:
        raise ValueError("invalid professional image receipt policy")
    return fields


def media_receipt(value: object, *, runtime_request_id: str, classroom_id: str,
                  build_item_id: str, session_id: str) -> dict[str, Any]:
    fields = {"schemaVersion", "status", "runtimeRequestId", "buildItemId", "classroomId",
              "sessionId", "policyId", "providerId", "modelId", "imageCount", "assets", "receiptSha256"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("invalid formal media receipt fields")
    receipt = deepcopy(dict(value))
    expected = {"schemaVersion": MEDIA_RECEIPT_SCHEMA, "status": "succeeded",
                "runtimeRequestId": runtime_request_id, "classroomId": classroom_id,
                "buildItemId": build_item_id, "sessionId": session_id,
                **{k: FORMAL_IMAGE_POLICY[k] for k in ("policyId", "providerId", "modelId")}}
    if any(receipt.get(k) != v for k, v in expected.items()):
        raise ValueError("formal media receipt identity mismatch")
    if any(not _IDENTIFIER.fullmatch(v) for v in (runtime_request_id, classroom_id, build_item_id, session_id)):
        raise ValueError("invalid formal media identity")
    assets = receipt.get("assets")
    if (not isinstance(assets, list) or type(receipt.get("imageCount")) is not int
            or receipt["imageCount"] != len(assets) or len(assets) > 120):
        raise ValueError("invalid formal media image count")
    seen: set[str] = set()
    prefix = f"/api/classroom-media/{classroom_id}/media/"
    for asset in assets:
        if not isinstance(asset, Mapping) or set(asset) != {"src", "sha256", "mimeType", "byteSize", "width", "height", "sceneIds"}:
            raise ValueError("invalid formal image asset fields")
        src = asset.get("src")
        digest = asset.get("sha256")
        if (not isinstance(src, str) or not src.startswith(prefix)
                or not re.fullmatch(r"[A-Za-z0-9_-]+\.(?:png|jpe?g|webp|gif)", src[len(prefix):])
                or src in seen or not isinstance(digest, str) or not _SHA.fullmatch(digest)
                or asset.get("mimeType") not in _IMAGE_TYPES):
            raise ValueError("invalid formal image asset identity")
        filename = src[len(prefix):]
        if filename.startswith("generated-") and filename.split(".")[0] != f"generated-{digest}":
            raise ValueError("generated image digest mismatch")
        for field, maximum in (("byteSize", 32 * 1024 * 1024), ("width", 32768), ("height", 32768)):
            if type(asset.get(field)) is not int or not 1 <= asset[field] <= maximum:
                raise ValueError("invalid formal image dimensions or size")
        scene_ids = asset.get("sceneIds")
        if (not isinstance(scene_ids, list) or not scene_ids or len(scene_ids) > 60
                or any(not isinstance(s, str) or not _IDENTIFIER.fullmatch(s) for s in scene_ids)
                or len(set(scene_ids)) != len(scene_ids)):
            raise ValueError("invalid formal image scene binding")
        seen.add(src)
    digest = receipt.pop("receiptSha256")
    if not isinstance(digest, str) or not _SHA.fullmatch(digest) or canonical_sha256(receipt) != digest:
        raise ValueError("formal media receipt digest mismatch")
    receipt["receiptSha256"] = digest
    return receipt


def _srcset_image_sources(value: str) -> list[str]:
    """Match the Runtime's parse-srcset URL and descriptor tokenization.

    A URL ends at ASCII whitespace, not at each comma: data URLs and ordinary
    image URLs may contain commas. Only trailing URL commas and descriptor
    delimiters separate candidates.
    """
    spaces = " \t\n\r\f"
    sources: list[str] = []
    position = 0
    while position < len(value):
        while position < len(value) and value[position] in spaces + ",":
            position += 1
        start = position
        while position < len(value) and value[position] not in spaces:
            position += 1
        url = value[start:position]
        if not url:
            break
        descriptors: list[str] = []
        if url.endswith(","):
            url = url.rstrip(",")
        else:
            descriptor = ""
            in_parens = False
            while position < len(value):
                char = value[position]
                position += 1
                if in_parens:
                    descriptor += char
                    if char == ")":
                        in_parens = False
                elif char == ",":
                    break
                elif char in spaces:
                    if descriptor:
                        descriptors.append(descriptor)
                        descriptor = ""
                else:
                    descriptor += char
                    in_parens = char == "("
            if descriptor:
                descriptors.append(descriptor)

        width = height = False
        density = 0.0
        valid = True
        for descriptor in descriptors:
            number, kind = descriptor[:-1], descriptor[-1:]
            if kind in {"w", "h"} and re.fullmatch(r"[0-9]+", number):
                nonzero = bool(number.lstrip("0"))
                if density or (width if kind == "w" else height) or not nonzero:
                    valid = False
                if kind == "w":
                    width = nonzero
                else:
                    height = nonzero
            elif kind == "x" and re.fullmatch(r"-?(?:[0-9]+|[0-9]*\.[0-9]+)(?:[eE][+-]?[0-9]+)?", number):
                candidate_density = float(number)
                if width or height or density or candidate_density < 0:
                    valid = False
                else:
                    density = candidate_density
            else:
                valid = False
        if valid:
            sources.append(url)
    return sources


class _ImageHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes: dict[str, str | None] = {}
        for key, value in attrs:
            attributes.setdefault(key, value)
        if tag in {"img", "image"}:
            source = attributes.get("src") or attributes.get("href") or attributes.get("xlink:href")
            if source:
                self.sources.add(source)
        if tag in {"img", "source"} and attributes.get("srcset"):
            self.sources.update(_srcset_image_sources(attributes["srcset"]))


def classroom_image_references(classroom: Mapping[str, Any]) -> dict[str, set[str]]:
    references: dict[str, set[str]] = {}

    def visit(value: object, scene_id: str) -> None:
        if isinstance(value, Mapping):
            if value.get("type") == "image":
                if not isinstance(value.get("src"), str) or not value["src"].strip():
                    raise ValueError("formal image source is missing")
                references.setdefault(value["src"], set()).add(scene_id)
            if value.get("type") == "video" and value.get("poster"):
                if not isinstance(value["poster"], str):
                    raise ValueError("formal video poster source is invalid")
                references.setdefault(value["poster"], set()).add(scene_id)
            for item in value.values():
                visit(item, scene_id)
        elif isinstance(value, list):
            for item in value:
                visit(item, scene_id)
        elif isinstance(value, str):
            if value.startswith("/api/classroom-media/") and re.search(r"\.(?:png|jpe?g|webp|gif)$", value):
                references.setdefault(value, set()).add(scene_id)
            if "<" in value:
                parser = _ImageHTMLParser()
                parser.feed(value)
                for src in parser.sources:
                    # HTMLParser already decodes attribute character references.
                    references.setdefault(src, set()).add(scene_id)
            for match in re.finditer(r"url\(\s*['\"]?([^'\")\s]+)['\"]?\s*\)", value, re.I):
                src = unescape(match.group(1))
                if not src.startswith("#"):
                    references.setdefault(src, set()).add(scene_id)

    scenes = classroom.get("scenes")
    if not isinstance(scenes, list):
        raise ValueError("formal image classroom scenes missing")
    for scene in scenes:
        if not isinstance(scene, Mapping) or not isinstance(scene.get("id"), str):
            raise ValueError("formal image scene identity missing")
        visit(scene, scene["id"])
    return references


def media_evidence(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {"verified": True, **{key: receipt[key] for key in (
        "schemaVersion", "policyId", "providerId", "modelId", "imageCount", "receiptSha256")},
        "verifiedAssetCount": len(receipt["assets"])}


def validate_classroom_media(receipt: Mapping[str, Any], classroom: Mapping[str, Any],
                             probe: Callable[[str], bool]) -> dict[str, Any]:
    if not isinstance(classroom.get("stage"), Mapping) or classroom["stage"].get("id") != receipt["classroomId"]:
        raise ValueError("formal image classroom mismatch")
    references = classroom_image_references(classroom)
    if set(references) != {asset["src"] for asset in receipt["assets"]}:
        raise ValueError("formal classroom image receipt coverage mismatch")
    for asset in receipt["assets"]:
        if references[asset["src"]] != set(asset["sceneIds"]):
            raise ValueError("formal image scene reference mismatch")
        if not probe(asset["src"]):
            raise ValueError("formal image asset unavailable")
    return media_evidence(receipt)


def validate_media_manifest(manifest: Mapping[str, Any]) -> dict[str, Any] | None:
    """Recheck persisted policy, identity and evidence before publication/launch."""
    generation = manifest.get("generationContract")
    professional = manifest.get("professionalCreation")
    evidence = manifest.get("formalEvidence")
    if not all(isinstance(v, Mapping) for v in (generation, professional, evidence)):
        raise ValueError("formal media authority missing")
    policy = professional_policy(generation.get("professionalCreationPolicy"))
    validate_generation_grade_boundary(generation)
    validate_skill_manifest(manifest)
    validate_quality_manifest(manifest)
    validate_video_manifest(manifest)
    if canonical_sha256(generation.get("generation")) != canonical_sha256(generation_options(policy)):
        raise ValueError("formal media generation options mismatch")
    image_fields = professional_image_fields(professional)
    if bool(image_fields) != ("image" in policy):
        raise ValueError("formal media professional policy mismatch")
    if not image_fields:
        if "media" in manifest or "media" in evidence:
            raise ValueError("legacy formal classroom cannot acquire media receipts")
        return None
    receipt = media_receipt(manifest.get("media"),
        runtime_request_id=professional["runtimeRequestId"],
        classroom_id=professional["classroomId"], build_item_id=professional["buildItemId"],
        session_id=professional["sessionId"])
    if evidence.get("media") != media_evidence(receipt):
        raise ValueError("formal media validation evidence mismatch")
    return receipt
