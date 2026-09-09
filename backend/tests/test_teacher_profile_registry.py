from __future__ import annotations

import json
import unittest
from dataclasses import replace

from content.teacher_profiles import (
    LEGACY_TEACHER_REGISTRY_VERSION,
    SUPPORTED_TEACHER_SUBJECTS,
    TEACHER_PROFILES,
    TEACHER_REGISTRY_VERSION,
    FORMAL_SUBJECT_QWEN_VOICE_CONTRACT_VERSION,
    get_formal_subject_qwen_voice_identity,
    get_openmaic_qwen3_voice_identity,
    get_teacher_profile,
    list_teacher_profiles,
    validate_teacher_registry,
    validate_formal_subject_qwen_voice_registry,
)


class TeacherProfileRegistryTest(unittest.TestCase):
    def test_registry_covers_primary_subjects_and_forbids_clone_material(self):
        validate_teacher_registry()
        self.assertEqual({profile.subject for profile in TEACHER_PROFILES}, SUPPORTED_TEACHER_SUBJECTS)
        for profile in TEACHER_PROFILES:
            self.assertEqual(profile.voice_mode, "prompt")
            self.assertFalse(profile.clone_allowed)
            payload = profile.to_storage_payload()
            self.assertNotIn("referenceAudio", payload)
            self.assertNotIn("registeredVoiceId", payload)
            self.assertEqual(len(profile.content_hash), 64)

    def test_legacy_v1_hashes_remain_immutable_and_v2_is_current(self):
        expected_v1_hashes = {
            "mira_chinese_gentle": "e2289e7ddfca40753d9636302673ed34db52dfc595cdba99448e313740dc22c2",
            "mira_math_clear": "7ef963250148bd13c48c59d366123af3571e14a3c46aecf93ab86c71e7ac4959",
            "mira_english_standard": "eca4b35b15d24adb5ca7385418723ef615adf15a705284e4bb4e1fb1a54b9213",
        }
        for profile_id, content_hash in expected_v1_hashes.items():
            legacy = get_teacher_profile(profile_id, 1)
            current = get_teacher_profile(profile_id)
            self.assertEqual(legacy.registry_version, LEGACY_TEACHER_REGISTRY_VERSION)
            self.assertEqual(legacy.provider_model, "voxcpm2")
            self.assertEqual(legacy.content_hash, content_hash)
            self.assertEqual(current.version, 2)
            self.assertEqual(current.registry_version, TEACHER_REGISTRY_VERSION)
            self.assertEqual(current.provider_model, "openbmb/VoxCPM2")
            self.assertNotEqual(current.content_hash, legacy.content_hash)

    def test_public_profile_hides_provider_and_voice_prompt(self):
        profile = get_teacher_profile("mira_chinese_gentle")
        public = profile.to_public_payload()
        self.assertEqual(public["version"], 2)
        self.assertEqual(public["displayName"], "小语老师")
        self.assertEqual(public["avatarPath"], "/teachers/mi-chinese-v1.png")
        self.assertNotIn("providerId", public)
        self.assertNotIn("providerModel", public)
        self.assertNotIn("voicePrompt", public)

    def test_subject_filter_returns_only_the_subject_teacher(self):
        profiles = list_teacher_profiles(subject="english")
        self.assertEqual([profile.profile_id for profile in profiles], ["mira_english_standard"])
        self.assertEqual([profile.version for profile in profiles], [2])
        all_versions = list_teacher_profiles(
            subject="english",
            include_legacy_versions=True,
        )
        self.assertEqual([profile.version for profile in all_versions], [1, 2])

    def test_private_runtime_binding_keeps_public_teacher_identity_stable(self):
        profile = get_teacher_profile("mira_math_clear", 1)
        binding = profile.bind_tts_provider(
            provider_id="macos-say",
            provider_model="apple/macos-system-speech",
        )
        self.assertEqual(binding.teacher_profile_id, "mira_math_clear")
        self.assertEqual(binding.teacher_profile_version, 1)
        self.assertEqual(binding.provider_id, "macos-say")
        self.assertEqual(binding.provider_model, "apple/macos-system-speech")
        self.assertNotIn("providerId", profile.to_public_payload())

    def test_openmaic_sample_teacher_has_a_credential_free_qwen3_identity(self):
        identity = get_openmaic_qwen3_voice_identity("mira_math_clear", 2)
        payload = identity.to_runtime_payload()
        self.assertEqual(
            payload["voiceConfig"],
            {
                "providerId": "qwen-tts",
                "modelId": "qwen3-tts-flash",
                "voiceId": "Serena",
            },
        )
        self.assertEqual(payload["selectionId"], "qwen-tts::Serena")
        serialized = json.dumps(payload, ensure_ascii=False).casefold()
        self.assertNotIn("apikey", serialized)
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("baseurl", serialized)
        with self.assertRaises(KeyError):
            get_openmaic_qwen3_voice_identity("mira_math_clear", 1)

    def test_formal_subject_voices_are_gender_consistent_and_sample_is_isolated(self):
        expected = {
            "chinese": {
                "profileId": "mira_chinese_gentle",
                "profileVersion": 2,
                "profileHash": "a5fd163af249705bda4bb0be5448f65d275eb423285557727f9c50ea442f01f8",
                "teacherName": "小语老师",
                "teacherGender": "female",
                "voiceGender": "female",
                "voiceId": "Serena",
                "languageCode": "zh-CN",
            },
            "math": {
                "profileId": "mira_math_clear",
                "profileVersion": 2,
                "profileHash": "4f5a986a765f69798c8546d7f9091fe297f2a98c5353fdd01cd1aa06884c98fb",
                "teacherName": "小数老师",
                "teacherGender": "male",
                "voiceGender": "male",
                "voiceId": "Ethan",
                "languageCode": "zh-CN",
            },
            "english": {
                "profileId": "mira_english_standard",
                "profileVersion": 2,
                "profileHash": "4725f27c5438c0f68fe8923ac977fa1dd01452b990ac58912b880320750ee040",
                "teacherName": "Mia 老师",
                "teacherGender": "female",
                "voiceGender": "female",
                "voiceId": "Jennifer",
                "languageCode": "en-US",
            },
        }
        actual = {
            subject: get_formal_subject_qwen_voice_identity(subject).to_target_payload()
            for subject in expected
        }
        for subject, expected_identity in expected.items():
            payload = actual[subject]
            self.assertEqual(payload["schemaVersion"], FORMAL_SUBJECT_QWEN_VOICE_CONTRACT_VERSION)
            self.assertEqual(payload["teacherProfile"], {
                "id": expected_identity["profileId"],
                "version": expected_identity["profileVersion"],
                "contentHash": expected_identity["profileHash"],
            })
            for key in ("teacherName", "teacherGender", "voiceGender", "voiceId", "languageCode"):
                self.assertEqual(payload[key], expected_identity[key])
            self.assertEqual(payload["tts"], {
                "providerId": "qwen-tts",
                "modelId": "qwen3-tts-flash",
                "fallbackAllowed": False,
            })
            self.assertEqual(payload["asr"], {
                "providerId": "qwen-asr",
                "modelId": "qwen3-asr-flash",
                "fallbackAllowed": False,
            })
        self.assertEqual(
            get_openmaic_qwen3_voice_identity("mira_math_clear", 2).voice_id,
            "Serena",
        )
        self.assertEqual(actual["math"]["voiceId"], "Ethan")

    def test_formal_subject_voice_registry_rejects_identity_mutations(self):
        identities = {
            subject: get_formal_subject_qwen_voice_identity(subject)
            for subject in ("chinese", "math", "english")
        }
        for field, invalid in (
            ("teacher_gender", "female"),
            ("voice_gender", "female"),
            ("voice_id", "Serena"),
            ("language_code", "en-US"),
            ("fallback_allowed", True),
        ):
            mutated = dict(identities)
            mutated["math"] = replace(identities["math"], **{field: invalid})
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_formal_subject_qwen_voice_registry(mutated)


if __name__ == "__main__":
    unittest.main()
