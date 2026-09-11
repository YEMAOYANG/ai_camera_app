from __future__ import annotations

import copy
import hashlib
import unittest

from integrations.openmaic_formal_quality import quality_sha
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError
from tests.test_openmaic_formal_audio_v2_client import _formal_audio


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _sign(audio: dict) -> None:
    sidecar = audio["segments"][0]["asr"]["comparisonRevalidation"]
    for key in ("asrRecord", "ttsRecord", "transcriptArchive"):
        sidecar["source"][key + "Sha256"] = quality_sha(sidecar["source"][key])
    sidecar["receiptSha256"] = quality_sha({key: value for key, value in sidecar.items() if key != "receiptSha256"})
    audio["receiptSha256"] = quality_sha({key: value for key, value in audio.items() if key != "receiptSha256"})


def _fixture() -> tuple[dict, dict]:
    audio = _formal_audio(1)
    segment, teacher = audio["segments"][0], audio["teacherProfile"]
    segment["textSha256"] = _sha("3/5")
    segment["asr"].update(transcriptSha256=_sha("五分之三"), normalizedTranscriptSha256=_sha("五分之三"), similarityBps=10000)
    common = {
        "schemaVersion": "mira.openmaic.formal-audio-job.v1", "classroomId": audio["classroomId"],
        "classroomContentSha256": audio["classroomContentSha256"], "subject": "math",
        "teacherProfileId": teacher["id"], "teacherProfileVersion": teacher["version"],
        "teacherProfileSha256": teacher["sha256"], "teacherGender": teacher["gender"],
        **{key: segment[key] for key in ("sceneId", "sceneOrder", "actionId", "narrationSegmentId")},
        **{key: "2026-09-10T00:00:00.000Z" for key in ("createdAt", "updatedAt", "completedAt", "providerAttemptedAt", "providerCompletedAt")},
        "languageCode": "zh-CN",
    }
    tts = {**common, **segment["tts"], "kind": "tts", "textSha256": segment["textSha256"], "voiceGender": "male",
        "downloadAttemptedAt": common["completedAt"], "assetId": "mirawav_" + "a" * 24,
        "assetFileName": "mirawav_" + "a" * 24 + ".wav"}
    asr = {**common, **segment["asr"], "kind": "asr", "similarityBps": 8000,
        "normalizedTranscriptSha256": _sha("三除以五"), "ttsRequestId": tts["requestId"], "audioSha256": tts["audioSha256"]}
    professional = {"sessionId": "miraformal_" + "b" * 64, "classroomId": audio["classroomId"], "buildItemId": audio["buildItemId"],
        "teachingQuality": {"sessionId": "miraformal_" + "b" * 64, "stageId": audio["classroomId"], "snapshotSha256": "c" * 64, "status": "passed"}}
    sidecar = {
        "schemaVersion": "mira.openmaic.asr-comparison-revalidation.v1",
        "binding": {"sessionId": professional["sessionId"], "stageId": audio["classroomId"], "snapshotSha256": "c" * 64,
            "sourceJobSha256": "d" * 64, "asrRequestId": asr["requestId"]},
        "source": {"asrRecord": asr, "ttsRecord": tts, "spokenText": "3/5", "transcriptArchive": {
            "requestId": asr["requestId"], "audioSha256": tts["audioSha256"], "transcript": "五分之三", "transcriptSha256": asr["transcriptSha256"]}},
        "comparison": {"policyVersion": "mira.learning.formal-asr-comparison.v3-math-notation", "sourceSha256": "e" * 64,
            "normalizedTranscriptSha256": segment["asr"]["normalizedTranscriptSha256"], "similarityBps": 10000},
        "createdAt": common["completedAt"],
    }
    segment["asr"]["comparisonRevalidation"] = sidecar
    _sign(audio)
    return audio, professional


class AsrRevalidationClientTest(unittest.TestCase):
    def parse(self, audio, professional):
        return OpenMaicFullRuntimeClient._formal_audio_receipt_from_payload(
            audio, classroom_id=audio["classroomId"], expected_segment_count=1, professional_creation=professional)

    def test_accepts_audited_comparison_without_replacing_source_record(self):
        audio, professional = _fixture()
        frozen = copy.deepcopy(audio)
        parsed = self.parse(audio, professional).segments[0].asr
        self.assertEqual(parsed.similarity_bps, 10000)
        self.assertEqual(parsed.comparison_revalidation["source"]["asrRecord"]["similarityBps"], 8000)
        self.assertEqual(audio, frozen)

    def test_rejects_resigned_wrong_source_or_final_binding(self):
        changes = (
            lambda sidecar: sidecar["source"]["asrRecord"].update(state="failed"),
            lambda sidecar: sidecar["source"]["asrRecord"].update(similarityBps=9000),
            lambda sidecar: sidecar["source"]["ttsRecord"].update(audioSha256="f" * 64),
            lambda sidecar: sidecar["source"]["asrRecord"].update(actionId="another-action"),
            lambda sidecar: sidecar["source"].update(spokenText="5/3"),
            lambda sidecar: sidecar["source"]["transcriptArchive"].update(transcript="三分之五"),
            lambda sidecar: sidecar["binding"].update(snapshotSha256="f" * 64),
            lambda sidecar: sidecar["comparison"].update(policyVersion="unknown-policy"),
            lambda sidecar: sidecar["source"]["asrRecord"].update(operatorRepair={}),
        )
        for change in changes:
            with self.subTest(change=changes.index(change)):
                audio, professional = _fixture()
                change(audio["segments"][0]["asr"]["comparisonRevalidation"])
                _sign(audio)
                with self.assertRaises(OpenMaicFullRuntimeError):
                    self.parse(audio, professional)

    def test_rejects_unbound_or_hash_tampered_audit(self):
        audio, professional = _fixture()
        with self.assertRaises(OpenMaicFullRuntimeError):
            self.parse(audio, None)
        sidecar = audio["segments"][0]["asr"]["comparisonRevalidation"]
        sidecar["source"]["asrRecordSha256"] = "f" * 64
        sidecar["receiptSha256"] = quality_sha({key: value for key, value in sidecar.items() if key != "receiptSha256"})
        audio["receiptSha256"] = quality_sha({key: value for key, value in audio.items() if key != "receiptSha256"})
        with self.assertRaises(OpenMaicFullRuntimeError):
            self.parse(audio, professional)

    def test_optional_physical_pronunciation_must_bind_the_original_text(self):
        audio, professional = _fixture()
        source = audio["segments"][0]["asr"]["comparisonRevalidation"]["source"]
        source["ttsRecord"]["providerPronunciation"] = {
            "policyVersion": "mira.math.tts-pronunciation.v1",
            "sourceTextSha256": source["ttsRecord"]["textSha256"],
            "textSha256": _sha("五分之三"), "characters": 4, "providerBodySha256": "a" * 64,
        }
        _sign(audio)
        self.assertEqual(self.parse(audio, professional).segments[0].asr.similarity_bps, 10000)
        source["ttsRecord"]["providerPronunciation"]["sourceTextSha256"] = "f" * 64
        _sign(audio)
        with self.assertRaises(OpenMaicFullRuntimeError):
            self.parse(audio, professional)


if __name__ == "__main__":
    unittest.main()
