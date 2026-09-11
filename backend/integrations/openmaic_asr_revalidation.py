"""Validate the private audit sidecar for replaying an already paid ASR result.

Native replays the comparator against the original files and WAV on every read.
This boundary binds its receipt to the original records and the final classroom;
it never upgrades a provider failure or dispatches another audio request.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Mapping

from integrations.openmaic_formal_quality import quality_sha


COMPARISON_POLICY = "mira.learning.formal-asr-comparison.v3-math-notation"
_IDENTITY = {
    "classroomId", "classroomContentSha256", "subject", "teacherProfileId",
    "teacherProfileVersion", "teacherProfileSha256", "teacherGender", "sceneId",
    "sceneOrder", "actionId", "narrationSegmentId",
}
_BASE = _IDENTITY | {
    "schemaVersion", "kind", "requestId", "requestSha256", "state", "providerId",
    "modelId", "fallbackUsed", "providerAttemptedAt", "providerCompletedAt",
    "createdAt", "updatedAt", "completedAt", "languageCode",
}


def _exact(value: object, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError("invalid ASR comparison audit fields")
    return value


def _hash(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def validate_asr_comparison_revalidation(
    value: object, *, lifecycle: Mapping[str, Any], segment: Mapping[str, Any],
    professional_creation: object,
) -> dict[str, Any]:
    raw = _exact(value, {"schemaVersion", "binding", "source", "comparison", "createdAt", "receiptSha256"})
    binding = _exact(raw["binding"], {"sessionId", "stageId", "snapshotSha256", "sourceJobSha256", "asrRequestId"})
    source = _exact(raw["source"], {"asrRecord", "ttsRecord", "transcriptArchive", "spokenText",
        "asrRecordSha256", "ttsRecordSha256", "transcriptArchiveSha256"})
    comparison = _exact(raw["comparison"], {"policyVersion", "sourceSha256", "normalizedTranscriptSha256", "similarityBps"})
    original_asr = _exact(source["asrRecord"], _BASE | {"ttsRequestId", "audioSha256",
        "transcriptSha256", "normalizedTranscriptSha256", "similarityBps"})
    pronunciation_keys = {"providerPronunciation"} if isinstance(source["ttsRecord"], Mapping) and "providerPronunciation" in source["ttsRecord"] else set()
    original_tts = _exact(source["ttsRecord"], _BASE | {"textSha256", "voiceId", "voiceGender",
        "downloadAttemptedAt", "assetId", "assetFileName", "mimeType", "sizeBytes", "audioSha256"} | pronunciation_keys)
    if pronunciation_keys:
        pronunciation = _exact(original_tts["providerPronunciation"], {
            "policyVersion", "sourceTextSha256", "textSha256", "characters", "providerBodySha256"})
        if (pronunciation["policyVersion"] != "mira.math.tts-pronunciation.v1"
                or pronunciation["sourceTextSha256"] != original_tts["textSha256"]
                or not _hash(pronunciation["textSha256"])
                or not _hash(pronunciation["providerBodySha256"])
                or type(pronunciation["characters"]) is not int
                or not 1 <= pronunciation["characters"] <= 64000):
            raise ValueError("invalid physical TTS pronunciation audit")
    archive = _exact(source["transcriptArchive"], {"requestId", "audioSha256", "transcript", "transcriptSha256"})
    if not isinstance(professional_creation, Mapping):
        raise ValueError("ASR comparison audit lacks professional creation")
    quality = professional_creation.get("teachingQuality")
    if not isinstance(quality, Mapping):
        raise ValueError("ASR comparison audit lacks final quality snapshot")
    asr, tts, teacher = segment["asr"], segment["tts"], lifecycle["teacherProfile"]
    if (
        raw["schemaVersion"] != "mira.openmaic.asr-comparison-revalidation.v1"
        or not _timestamp(raw["createdAt"])
        or not _hash(raw["receiptSha256"])
        or quality_sha({key: item for key, item in raw.items() if key != "receiptSha256"}) != raw["receiptSha256"]
        or not isinstance(binding["sessionId"], str)
        or re.fullmatch(r"miraformal_[a-f0-9]{64}", binding["sessionId"]) is None
        or binding["sessionId"] != professional_creation.get("sessionId")
        or binding["sessionId"] != quality.get("sessionId")
        or binding["stageId"] != lifecycle["classroomId"]
        or binding["stageId"] != professional_creation.get("classroomId")
        or binding["stageId"] != quality.get("stageId")
        or professional_creation.get("buildItemId") != lifecycle["buildItemId"]
        or binding["snapshotSha256"] != quality.get("snapshotSha256")
        or quality.get("status") != "passed"
        or not _hash(binding["snapshotSha256"])
        or not _hash(binding["sourceJobSha256"])
        or binding["asrRequestId"] != asr["requestId"]
        or comparison["policyVersion"] != COMPARISON_POLICY
        or not _hash(comparison["sourceSha256"])
        or not _hash(comparison["normalizedTranscriptSha256"])
        or comparison["normalizedTranscriptSha256"] != asr["normalizedTranscriptSha256"]
        or type(comparison["similarityBps"]) is not int
        or not 8500 <= comparison["similarityBps"] <= 10000
        or comparison["similarityBps"] != asr["similarityBps"]
        or type(original_asr["similarityBps"]) is not int
        or not 0 <= original_asr["similarityBps"] < 8500
        or not _hash(original_asr["normalizedTranscriptSha256"])
        or lifecycle["subject"] != "math"
    ):
        raise ValueError("invalid ASR comparison audit identity")
    for key, record in (("asrRecord", original_asr), ("ttsRecord", original_tts), ("transcriptArchive", archive)):
        if not _hash(source[key + "Sha256"]) or quality_sha(record) != source[key + "Sha256"]:
            raise ValueError("ASR comparison source hash mismatch")
    expected_identity = {
        "classroomId": lifecycle["classroomId"], "classroomContentSha256": lifecycle["classroomContentSha256"],
        "subject": lifecycle["subject"], "teacherProfileId": teacher["id"],
        "teacherProfileVersion": teacher["version"], "teacherProfileSha256": teacher["sha256"],
        "teacherGender": teacher["gender"],
        **{key: segment[key] for key in ("sceneId", "sceneOrder", "actionId", "narrationSegmentId")},
    }
    for kind, original, final in (("asr", original_asr, asr), ("tts", original_tts, tts)):
        if (original["schemaVersion"] != "mira.openmaic.formal-audio-job.v1"
                or original["kind"] != kind
                or original["state"] != "succeeded" or original["fallbackUsed"] is not False
                or original["languageCode"] != "zh-CN"
                or type(original["sceneOrder"]) is not int or type(original["teacherProfileVersion"]) is not int
                or any(original[key] != expected for key, expected in expected_identity.items())
                or any(original[key] != final[key] for key in ("requestId", "requestSha256", "state", "providerId", "modelId", "fallbackUsed"))
                or any(not _timestamp(original[key]) for key in ("createdAt", "updatedAt", "completedAt", "providerAttemptedAt", "providerCompletedAt"))):
            raise ValueError("ASR comparison original provider identity mismatch")
    if (original_asr["ttsRequestId"] != tts["requestId"]
            or original_asr["audioSha256"] != tts["audioSha256"]
            or original_asr["transcriptSha256"] != asr["transcriptSha256"]
            or any(original_tts[key] != tts[key] for key in ("audioSha256", "mimeType", "sizeBytes", "voiceId"))
            or type(original_tts["sizeBytes"]) is not int
            or original_tts["voiceGender"] != teacher["gender"]
            or not _timestamp(original_tts["downloadAttemptedAt"])
            or not isinstance(original_tts["assetId"], str)
            or re.fullmatch(r"mirawav_[a-f0-9]{24}", original_tts["assetId"]) is None
            or original_tts["assetFileName"] != original_tts["assetId"] + ".wav"
            or not isinstance(source["spokenText"], str) or not 1 <= len(source["spokenText"]) <= 64000
            or _sha(source["spokenText"]) != segment["textSha256"]
            or original_tts["textSha256"] != segment["textSha256"]
            or archive["requestId"] != asr["requestId"]
            or archive["audioSha256"] != tts["audioSha256"]
            or archive["transcriptSha256"] != asr["transcriptSha256"]
            or not isinstance(archive["transcript"], str) or not 1 <= len(archive["transcript"]) <= 64000
            or _sha(archive["transcript"]) != archive["transcriptSha256"]):
        raise ValueError("ASR comparison original audio or transcript mismatch")
    return dict(raw)
