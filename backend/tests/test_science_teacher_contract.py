from __future__ import annotations

import hashlib
import json
import copy
import unittest

from content.teacher_profiles import (
    SCIENCE_TEACHER_REGISTRY_VERSION,
    SUPPORTED_TEACHER_SUBJECTS,
    TEACHER_PROFILES,
    get_formal_runtime_teacher_contract,
    get_formal_subject_qwen_voice_identity,
    get_teacher_profile,
    list_teacher_profiles,
    validate_formal_subject_qwen_voice_registry,
    validate_science_teacher_contract,
    validate_teacher_registry,
)
from integrations.openmaic_full_runtime_client import (
    OpenMaicFullRuntimeClient,
    OpenMaicFullRuntimeError,
)


class RecordingAudioClient(OpenMaicFullRuntimeClient):
    def __init__(self):
        super().__init__("http://127.0.0.1:3100", formal_audio_internal_token="i" * 32)
        self.calls = []

    def _request_json(self, method, path, body=None, **kwargs):
        self.calls.append((method, path, body))
        if path.endswith("/asr"):
            text = "观察叶子的形状。"
            return {"success": True, "requestId": body["requestId"], "state": "succeeded",
                    "transcript": text, "transcriptSha256": hashlib.sha256(text.encode()).hexdigest()}
        return {"success": True, "requestId": body["requestId"], "state": "succeeded",
                "audioSha256": "2" * 64, "mimeType": "audio/wav"}


class ScienceTeacherContractTest(unittest.TestCase):
    def test_science_has_a_distinct_frozen_mandarin_teacher_and_qwen_contract(self):
        validate_science_teacher_contract()
        profile = get_teacher_profile("mira_science_inquiry")
        voice = get_formal_subject_qwen_voice_identity("science")
        contract = get_formal_runtime_teacher_contract("science")
        self.assertEqual(profile.registry_version, SCIENCE_TEACHER_REGISTRY_VERSION)
        self.assertEqual((profile.subject, profile.version, profile.display_name), ("science", 1, "小科老师"))
        self.assertEqual(profile.content_hash, "6bdd6746ed1a6a538751f23ff663a9153e7d1db767f7d9d3b6e5dc00d97d5c6b")
        self.assertEqual(voice.teacher_profile_hash, profile.content_hash)
        self.assertEqual((voice.voice_id, voice.language_code), ("Serena", "zh-CN"))
        self.assertEqual(voice.teacher_gender, voice.voice_gender)
        self.assertFalse(voice.fallback_allowed)
        self.assertEqual(contract["runtime"]["name"], "小科老师")
        self.assertEqual(contract["runtime"]["voiceConfig"], {
            "providerId": "qwen-tts", "modelId": "qwen3-tts-flash", "voiceId": "Serena"})
        self.assertEqual(voice.to_target_payload()["asr"], {
            "providerId": "qwen-asr", "modelId": "qwen3-asr-flash", "fallbackAllowed": False})
        self.assertEqual(list_teacher_profiles(subject="science"), (profile,))
        safe = json.dumps(contract, ensure_ascii=False).lower()
        self.assertNotIn("apikey", safe)
        self.assertNotIn("baseurl", safe)

    def test_addition_preserves_all_six_historical_profile_hashes_and_legacy_registry(self):
        validate_teacher_registry()
        validate_formal_subject_qwen_voice_registry()
        self.assertEqual({p.subject for p in TEACHER_PROFILES}, SUPPORTED_TEACHER_SUBJECTS)
        self.assertEqual({p.subject for p in list_teacher_profiles()}, SUPPORTED_TEACHER_SUBJECTS)
        expected = {
            ("mira_chinese_gentle", 1): "e2289e7ddfca40753d9636302673ed34db52dfc595cdba99448e313740dc22c2",
            ("mira_chinese_gentle", 2): "a5fd163af249705bda4bb0be5448f65d275eb423285557727f9c50ea442f01f8",
            ("mira_math_clear", 1): "7ef963250148bd13c48c59d366123af3571e14a3c46aecf93ab86c71e7ac4959",
            ("mira_math_clear", 2): "4f5a986a765f69798c8546d7f9091fe297f2a98c5353fdd01cd1aa06884c98fb",
            ("mira_english_standard", 1): "eca4b35b15d24adb5ca7385418723ef615adf15a705284e4bb4e1fb1a54b9213",
            ("mira_english_standard", 2): "4725f27c5438c0f68fe8923ac977fa1dd01452b990ac58912b880320750ee040",
        }
        for key, expected_hash in expected.items():
            with self.subTest(key=key):
                self.assertEqual(get_teacher_profile(*key).content_hash, expected_hash)

    @staticmethod
    def identity():
        voice = get_formal_subject_qwen_voice_identity("science")
        return {
            "classroom_id": "science-classroom", "classroom_content_sha256": "0" * 64,
            "subject": "science", "teacher_profile_id": voice.teacher_profile_id,
            "teacher_profile_version": voice.teacher_profile_version,
            "teacher_profile_sha256": voice.teacher_profile_hash, "teacher_gender": voice.teacher_gender,
            "scene_id": "science-scene", "scene_order": 0,
            "action_id": "science-speech", "narration_segment_id": "science-speech",
        }

    def test_science_tts_and_asr_use_exact_identity_without_client_provider_overrides(self):
        client = RecordingAudioClient()
        text = "观察叶子的形状。"
        tts = client.start_formal_audio_tts(request_id="science-tts", **self.identity(),
            text=text, text_sha256=hashlib.sha256(text.encode()).hexdigest())
        asr = client.start_formal_audio_asr(request_id="science-asr", tts_request_id="science-tts",
            **self.identity(), audio_sha256=tts["audioSha256"])
        self.assertEqual(asr["status"], "succeeded")
        self.assertEqual([c[1] for c in client.calls], ["/api/mira/formal-audio/tts", "/api/mira/formal-audio/asr"])
        for _, _, body in client.calls:
            self.assertEqual(body["subject"], "science")
            self.assertEqual(body["teacherProfileId"], "mira_science_inquiry")
            self.assertEqual(body["teacherProfileVersion"], 1)
            self.assertTrue({"voice", "provider", "model", "fallback", "apiKey", "baseUrl"}.isdisjoint(body))

    def test_other_teacher_wrong_version_hash_and_gender_are_rejected_before_dispatch(self):
        text = "观察叶子的形状。"
        for field, value in (("teacher_profile_id", "mira_chinese_gentle"),
                             ("teacher_profile_version", 2), ("teacher_profile_sha256", "1" * 64),
                             ("teacher_gender", "male"), ("subject", "history")):
            client = RecordingAudioClient()
            identity = {**self.identity(), field: value}
            with self.subTest(field=field), self.assertRaises(OpenMaicFullRuntimeError):
                client.start_formal_audio_tts(request_id="science-invalid", **identity,
                    text=text, text_sha256=hashlib.sha256(text.encode()).hexdigest())
            self.assertEqual(client.calls, [])

    def test_science_lifecycle_receipt_requires_registered_voice_and_exact_teacher_identity(self):
        voice = get_formal_subject_qwen_voice_identity("science")
        receipt = {
            "schemaVersion": OpenMaicFullRuntimeClient.FORMAL_AUDIO_LIFECYCLE_VERSION,
            "status": "succeeded", "buildItemId": "science-build", "classroomId": "science-classroom",
            "classroomContentSha256": "0" * 64, "subject": "science",
            "speechTextPolicyVersion": OpenMaicFullRuntimeClient.FORMAL_SPEECH_TEXT_POLICY_VERSION,
            "teacherProfile": {"id": voice.teacher_profile_id, "version": 1,
                               "sha256": voice.teacher_profile_hash, "gender": "female"},
            "expectedSegmentCount": 1, "ttsSucceededCount": 1, "asrPassedCount": 1,
            "segments": [{"sceneOrder": 0, "sceneId": "science-scene", "actionId": "science-speech",
                          "narrationSegmentId": "science-speech", "sourceTextSha256": "1" * 64,
                          "textSha256": "1" * 64,
                          "tts": {"requestId": "science-tts", "requestSha256": "2" * 64,
                                  "state": "succeeded", "audioSha256": "3" * 64, "mimeType": "audio/wav",
                                  "sizeBytes": 48, "providerId": "qwen-tts", "modelId": "qwen3-tts-flash",
                                  "voiceId": "Serena", "fallbackUsed": False},
                          "asr": {"requestId": "science-asr", "requestSha256": "4" * 64,
                                  "state": "succeeded", "transcriptSha256": "5" * 64,
                                  "normalizedTranscriptSha256": "6" * 64, "similarityBps": 10000,
                                  "providerId": "qwen-asr", "modelId": "qwen3-asr-flash",
                                  "fallbackUsed": False}}],
        }

        def parse(unsigned):
            digest = hashlib.sha256(json.dumps(unsigned, ensure_ascii=False, sort_keys=True,
                                               separators=(",", ":")).encode()).hexdigest()
            return OpenMaicFullRuntimeClient._formal_audio_receipt_from_payload(
                {**unsigned, "receiptSha256": digest}, classroom_id="science-classroom", expected_segment_count=1)

        parsed = parse(receipt)
        self.assertEqual((parsed.subject, parsed.teacher_profile_id), ("science", "mira_science_inquiry"))
        self.assertEqual(parsed.segments[0].tts.voice_id, "Serena")
        for field, value in (("id", "mira_chinese_gentle"), ("version", 2), ("sha256", "7" * 64),
                             ("gender", "male")):
            changed = copy.deepcopy(receipt)
            changed["teacherProfile"][field] = value
            with self.subTest(field=field), self.assertRaises(OpenMaicFullRuntimeError):
                parse(changed)
        changed = copy.deepcopy(receipt)
        changed["segments"][0]["tts"]["voiceId"] = "Ethan"
        with self.assertRaises(OpenMaicFullRuntimeError):
            parse(changed)


if __name__ == "__main__":
    unittest.main()
