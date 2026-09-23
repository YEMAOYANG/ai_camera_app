"""Validate the private audit sidecar for replaying an already paid ASR result.

Native replays the comparator against the original files and WAV on every read.
This boundary binds its receipt to the original records and the final classroom;
it never upgrades a provider failure or dispatches another audio request.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime
from typing import Any, Mapping

from integrations.openmaic_formal_quality import quality_sha


COMPARISON_POLICY = "mira.learning.formal-asr-comparison.v3-math-notation"
ENGLISH_SCHEMA = "mira.openmaic.asr-comparison-revalidation.v2-english-orthography"
ENGLISH_POLICY = "mira.learning.formal-asr-comparison.v1-english-name-orthography"
_ENGLISH_COMPARATOR_SHA = "ca4e93f89f56b430c4e69854a00a77abded04f9818622d229b6e67499df7237c"
_ENGLISH_BINDING = {
    "sessionId": "miraformal_06fd3faa925c2d7d2c7cbdc7b983f10fff1dead09ca3b2865d304bf3af33b1ae",
    "stageId": "stage-FC2nTYOIET",
    "snapshotSha256": "f678e29bd3954cca3db49820fda9a58974677259e5913e7d2a262b98a5f93904",
    "sourceJobSha256": "a3fb84e1c4e1f16424aa255b9f035453109b7103a7d61c609cfcdff41aaec037",
    "asrRequestId": "formal_asr_6041228c0db83966b76f926f2cf20ff85d75cb1a1c9e97f1",
}
_ENGLISH_SOURCE_HASHES = {
    "asrRecordSha256": "fc3923c725aeb480d89235f728f153a75416c97fe5bfb43cce7586c253381e48",
    "ttsRecordSha256": "cd3b0d0558f82a3f6a2b7b7b608b148efcfd3b3bfa3c2153688f339be9fd7e5c",
    "transcriptArchiveSha256": "9f7c2a3bc223afc855339e8d9452a2f12d26b05894bf52bc89032fa719fc586b",
}
_ENGLISH_RULES = [
    {"side": "expected", "from": "Mila", "to": "米拉", "occurrences": 1},
    {"side": "transcript", "from": "女孩儿", "to": "女孩", "occurrences": 1},
]
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


def _english_normalized(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", value).lower()
                   if unicodedata.category(c)[0] in {"L", "N"})


def _validate_exact_english(raw, lifecycle, segment):
    """One archived English segment, not a general name/grammar equivalence rule."""
    source, comparison = raw["source"], raw["comparison"]
    expected = "这位是女孩 Mila，她是主动发出问候动作的人。"
    transcript = "这位是女孩儿米拉，她是主动发出问候动作的人。"
    asr, tts = source["asrRecord"], source["ttsRecord"]
    if (raw["binding"] != _ENGLISH_BINDING or comparison["sourceSha256"] != _ENGLISH_COMPARATOR_SHA
            or any(source[key] != value for key, value in _ENGLISH_SOURCE_HASHES.items())
            or lifecycle["buildItemId"] != "catalog_build_item_d5a6b286d326400b49241b5d"
            or lifecycle["classroomContentSha256"] != "4808dd2c58c1e5fafec961e27a996052a872b551533570c9aabee0280ef81420"
            or segment["sceneId"] != "scene-p1" or segment["sceneOrder"] != 3
            or segment["actionId"] != "action_QNBwhwWM"
            or source["spokenText"] != expected or source["transcriptArchive"]["transcript"] != transcript
            or asr["similarityBps"] != 8095
            or asr["transcriptSha256"] != "ebf60d21d66a583b2205e618dbb84cebe21b25c87f0e320794571b7394ea6cab"
            or tts["textSha256"] != "ce99eade3e103be2eb037d545894170760a188450d8ab89167237e1aa05f2064"
            or tts["audioSha256"] != "6d24b9a487acc8be70d4fdc0e9a6ed87031526261c9b5cdabcae3aa2a00df5c5"
            or tts["sizeBytes"] != 234284 or quality_sha(comparison["appliedRules"]) != quality_sha(_ENGLISH_RULES)
            or comparison["similarityBps"] != 10000):
        raise ValueError("English ASR equivalence is outside the exact archived segment")
    # Recompute the original score, retaining its real 8095 result in source.
    left, right = _english_normalized(expected), _english_normalized(transcript)
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (a != b)))
        previous = current
    size = max(len(left), len(right))
    if (size - previous[-1]) * 10000 // size != 8095 or _sha(right) != asr["normalizedTranscriptSha256"]:
        raise ValueError("English ASR original comparison changed")
    if expected.count("Mila") != 1 or transcript.count("女孩儿") != 1:
        raise ValueError("English ASR equivalence occurrence mismatch")
    left = _english_normalized(expected.replace("Mila", "米拉"))
    right = _english_normalized(transcript.replace("女孩儿", "女孩"))
    if left != right or _sha(right) != comparison["normalizedTranscriptSha256"]:
        raise ValueError("English ASR equivalence does not match the complete sentence")


def validate_asr_comparison_revalidation(
    value: object, *, lifecycle: Mapping[str, Any], segment: Mapping[str, Any],
    professional_creation: object,
) -> dict[str, Any]:
    raw = _exact(value, {"schemaVersion", "binding", "source", "comparison", "createdAt", "receiptSha256"})
    english = raw["schemaVersion"] == ENGLISH_SCHEMA
    binding = _exact(raw["binding"], {"sessionId", "stageId", "snapshotSha256", "sourceJobSha256", "asrRequestId"})
    source = _exact(raw["source"], {"asrRecord", "ttsRecord", "transcriptArchive", "spokenText",
        "asrRecordSha256", "ttsRecordSha256", "transcriptArchiveSha256"})
    comparison = _exact(raw["comparison"], {"policyVersion", "sourceSha256", "normalizedTranscriptSha256", "similarityBps"}
                        | ({"appliedRules"} if english else set()))
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
        raw["schemaVersion"] != (ENGLISH_SCHEMA if english else "mira.openmaic.asr-comparison-revalidation.v1")
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
        or comparison["policyVersion"] != (ENGLISH_POLICY if english else COMPARISON_POLICY)
        or not _hash(comparison["sourceSha256"])
        or not _hash(comparison["normalizedTranscriptSha256"])
        or comparison["normalizedTranscriptSha256"] != asr["normalizedTranscriptSha256"]
        or type(comparison["similarityBps"]) is not int
        or not 8500 <= comparison["similarityBps"] <= 10000
        or comparison["similarityBps"] != asr["similarityBps"]
        or type(original_asr["similarityBps"]) is not int
        or not 0 <= original_asr["similarityBps"] < 8500
        or not _hash(original_asr["normalizedTranscriptSha256"])
        or lifecycle["subject"] != ("english" if english else "math")
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
                or original["languageCode"] != ("en-US" if english else "zh-CN")
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
    if english:
        _validate_exact_english(raw, lifecycle, segment)
    return dict(raw)
