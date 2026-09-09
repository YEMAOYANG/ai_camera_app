"""Versioned, same-classroom video evidence for formal Pro generation."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from html.parser import HTMLParser
import json
import re
from typing import Any, Callable, Mapping


FORMAL_VIDEO_POLICY = {
    "schemaVersion": "mira.openmaic.formal-video-policy.v1",
    "policyId": "mira-formal-happyhorse-video.v1",
    "enabled": True,
    "providerManaged": True,
    "providerId": "happyhorse",
    "modelId": "happyhorse-1.0-t2v",
    "usage": "teaching_need",
    "maxCalls": 1,
    "maxVideos": 1,
    "durationSec": 5,
    "resolution": "720p",
    "aspectRatio": "16:9",
    "assetValidationRequired": True,
}
VIDEO_RECEIPT_SCHEMA = "mira.openmaic.formal-video-receipt.v1"
_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,255}")
_SHA = re.compile(r"[0-9a-f]{64}")


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def professional_video_fields(value: Mapping[str, Any]) -> dict[str, Any]:
    fields = {key: value[key] for key in ("videoGenerationEnabled", "videoPolicyId") if key in value}
    expected = {"videoGenerationEnabled": True, "videoPolicyId": FORMAL_VIDEO_POLICY["policyId"]}
    if fields and _sha(fields) != _sha(expected):
        raise ValueError("invalid professional video receipt policy")
    return fields


def video_receipt(value: object, *, runtime_request_id: str, classroom_id: str,
                  build_item_id: str, session_id: str) -> dict[str, Any]:
    fields = {"schemaVersion", "status", "runtimeRequestId", "buildItemId", "classroomId",
              "sessionId", "policyId", "providerId", "modelId", "videoCount", "assets", "receiptSha256"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("invalid formal video receipt fields")
    receipt = deepcopy(dict(value))
    expected = {"schemaVersion": VIDEO_RECEIPT_SCHEMA, "status": "succeeded",
                "runtimeRequestId": runtime_request_id, "classroomId": classroom_id,
                "buildItemId": build_item_id, "sessionId": session_id,
                **{key: FORMAL_VIDEO_POLICY[key] for key in ("policyId", "providerId", "modelId")}}
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise ValueError("formal video receipt identity mismatch")
    if any(not isinstance(value, str) or not _IDENTIFIER.fullmatch(value)
           for value in (runtime_request_id, classroom_id, build_item_id, session_id)):
        raise ValueError("invalid formal video identity")
    assets = receipt.get("assets")
    if (not isinstance(assets, list) or type(receipt.get("videoCount")) is not int
            or receipt["videoCount"] != len(assets) or len(assets) > 1):
        raise ValueError("invalid formal video count")
    for asset in assets:
        if not isinstance(asset, Mapping) or set(asset) != {
            "src", "sha256", "mimeType", "byteSize", "width", "height", "durationMs", "sceneIds"
        }:
            raise ValueError("invalid formal video asset fields")
        digest = asset.get("sha256")
        if (not isinstance(digest, str) or not _SHA.fullmatch(digest)
                or asset.get("src") != f"/api/classroom-media/{classroom_id}/media/generated-{digest}.mp4"
                or asset.get("mimeType") != "video/mp4"):
            raise ValueError("invalid formal video asset identity")
        for field, minimum, maximum in (("byteSize", 1, 200 * 1024 * 1024),
                                        ("width", 1280, 1280), ("height", 720, 720),
                                        ("durationMs", 4900, 5100)):
            if type(asset.get(field)) is not int or not minimum <= asset[field] <= maximum:
                raise ValueError("invalid formal video dimensions, duration or size")
        scene_ids = asset.get("sceneIds")
        if (not isinstance(scene_ids, list) or not 1 <= len(scene_ids) <= 60
                or any(not isinstance(s, str) or not _IDENTIFIER.fullmatch(s) for s in scene_ids)
                or len(set(scene_ids)) != len(scene_ids)):
            raise ValueError("invalid formal video scene binding")
    digest = receipt.pop("receiptSha256")
    if not isinstance(digest, str) or not _SHA.fullmatch(digest) or _sha(receipt) != digest:
        raise ValueError("formal video receipt digest mismatch")
    receipt["receiptSha256"] = digest
    return receipt


class _VideoHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: set[str] = set()
        self.video_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes: dict[str, str | None] = {}
        for key, value in attrs:
            attributes.setdefault(key, value)
        if tag == "video":
            self.video_depth += 1
        if tag == "video" or (tag == "source" and self.video_depth):
            if attributes.get("src"):
                self.sources.add(attributes["src"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "video":
            self.video_depth = max(0, self.video_depth - 1)


def classroom_video_references(classroom: Mapping[str, Any]) -> dict[str, set[str]]:
    references: dict[str, set[str]] = {}

    def visit(value: object, scene_id: str) -> None:
        if isinstance(value, Mapping):
            if value.get("type") == "video":
                if not isinstance(value.get("src"), str) or not value["src"].strip():
                    raise ValueError("formal video source is missing")
                references.setdefault(value["src"], set()).add(scene_id)
            for child in value.values():
                visit(child, scene_id)
        elif isinstance(value, list):
            for child in value:
                visit(child, scene_id)
        elif isinstance(value, str) and "<" in value:
            parser = _VideoHTMLParser()
            parser.feed(value)
            for src in parser.sources:
                references.setdefault(src, set()).add(scene_id)

    scenes = classroom.get("scenes")
    if not isinstance(scenes, list):
        raise ValueError("formal video classroom scenes missing")
    for scene in scenes:
        if not isinstance(scene, Mapping) or not isinstance(scene.get("id"), str):
            raise ValueError("formal video scene identity missing")
        visit(scene, scene["id"])
    return references


def video_evidence(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {"verified": True, **{key: receipt[key] for key in (
        "schemaVersion", "policyId", "providerId", "modelId", "videoCount", "receiptSha256")},
        "verifiedAssetCount": len(receipt["assets"])}


def validate_classroom_video(receipt: Mapping[str, Any], classroom: Mapping[str, Any],
                             probe: Callable[[str], bool]) -> dict[str, Any]:
    if not isinstance(classroom.get("stage"), Mapping) or classroom["stage"].get("id") != receipt["classroomId"]:
        raise ValueError("formal video classroom mismatch")
    references = classroom_video_references(classroom)
    if set(references) != {asset["src"] for asset in receipt["assets"]}:
        raise ValueError("formal classroom video receipt coverage mismatch")
    for asset in receipt["assets"]:
        if references[asset["src"]] != set(asset["sceneIds"]):
            raise ValueError("formal video scene reference mismatch")
        if not probe(asset["src"]):
            raise ValueError("formal video asset unavailable")
    return video_evidence(receipt)


def validate_video_manifest(manifest: Mapping[str, Any]) -> dict[str, Any] | None:
    generation, professional, evidence = (manifest.get(key) for key in (
        "generationContract", "professionalCreation", "formalEvidence"))
    if not all(isinstance(value, Mapping) for value in (generation, professional, evidence)):
        raise ValueError("formal video authority missing")
    policy = generation.get("professionalCreationPolicy")
    if not isinstance(policy, Mapping):
        raise ValueError("formal video policy missing")
    fields = professional_video_fields(professional)
    if bool(fields) != ("video" in policy):
        raise ValueError("formal video professional policy mismatch")
    if not fields:
        if "video" in manifest or "video" in evidence:
            raise ValueError("legacy formal classroom cannot acquire video receipts")
        return None
    if _sha(policy["video"]) != _sha(FORMAL_VIDEO_POLICY):
        raise ValueError("unsupported formal video policy")
    receipt = video_receipt(manifest.get("video"), runtime_request_id=professional["runtimeRequestId"],
        classroom_id=professional["classroomId"], build_item_id=professional["buildItemId"],
        session_id=professional["sessionId"])
    if evidence.get("video") != video_evidence(receipt):
        raise ValueError("formal video validation evidence mismatch")
    return receipt
