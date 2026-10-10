"""The explicit English v2 lane preserves old plans, WAVs and uncertainty."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from content.teacher_profiles import get_formal_subject_qwen_voice_identity
from content.textbook_audio_language import ENGLISH_AUTO_LANGUAGE_POLICY_SHA256
from content.textbook_catalog import digest
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError
from scripts.narrate_textbook_batch import main
from services.textbook_batch_audio import (ENGLISH_AUTO_LANGUAGE_OPTION, ENGLISH_AUTO_LANGUAGE_POLICY,
    _asr_request_id, _segment_requests, build_audio_plan, narrate_candidate)
from tests import test_textbook_batch_audio as audio_fixture


class TextbookEnglishAutoLanguageTest(unittest.TestCase):
    def setUp(self):
        self.fixture = audio_fixture.TextbookBatchAudioTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.binding["subject"] = "english"
        self.teacher = get_formal_subject_qwen_voice_identity("english")
        self.runtime = self.fixture.runtime()

    def plan(self, option=ENGLISH_AUTO_LANGUAGE_OPTION):
        return build_audio_plan(self.fixture.room, self.fixture.binding, self.runtime.base_url,
                                audio_language_policy=option)

    def narrate(self, **kwargs):
        return narrate_candidate(self.runtime, self.fixture.room, self.fixture.binding,
            self.fixture.output, self.fixture.store, audio_language_policy=ENGLISH_AUTO_LANGUAGE_OPTION, **kwargs)

    def test_default_plan_and_ids_are_exact_legacy_values(self):
        legacy = self.plan(None)
        self.assertEqual(set(legacy), {"schemaVersion", "binding", "classroomId", "sourceSha256",
            "coreSha256", "teacher", "workload", "runtimeOrigin", "publicationAllowed"})
        self.assertEqual(legacy["schemaVersion"], "mira.textbook.batch-audio.v1")
        item = legacy["workload"][0]
        tts, identity, _, payload = _segment_requests(legacy, item, self.teacher)
        self.assertEqual(tts, "tbbtts_" + digest({"plan": digest(legacy), "segment": item}))
        self.assertEqual(_asr_request_id(legacy, tts, "a" * 64),
                         "tbbasr_" + digest({"tts": tts, "audio": "a" * 64}))
        self.assertNotIn("providerLanguagePolicy", payload)
        auto = self.plan()
        self.assertEqual(auto["workload"], legacy["workload"])
        self.assertEqual(auto["teacher"], legacy["teacher"])
        self.assertEqual(auto["sourceSha256"], legacy["sourceSha256"])
        self.assertEqual(auto["providerLanguagePolicySha256"], digest(ENGLISH_AUTO_LANGUAGE_POLICY))
        self.assertEqual(auto["schemaVersion"], "mira.textbook.batch-audio.v2")
        new_id, new_identity, _, new_payload = _segment_requests(auto, item, self.teacher)
        self.assertRegex(new_id, r"^tbbtts2_[0-9a-f]{64}$")
        self.assertNotEqual(new_id, tts)
        self.assertEqual(new_identity, identity)
        self.assertEqual(set(new_payload), set(payload))
        self.assertRegex(_asr_request_id(auto, new_id, "a" * 64), r"^tbbasr2_[0-9a-f]{64}$")

    def test_unknown_policy_wrong_subject_and_tampered_v2_plan_are_rejected(self):
        with self.assertRaises(ValueError): self.plan("arbitrary-auto")
        self.fixture.binding["subject"] = "math"
        with self.assertRaises(ValueError): self.plan()
        self.fixture.binding["subject"] = "english"
        plan = self.plan()
        plan["providerLanguagePolicy"]["tts"]["languageType"] = "English"
        with self.assertRaises(ValueError): _segment_requests(plan, plan["workload"][0], self.teacher)
        plan = self.plan(None)
        plan["providerLanguagePolicy"] = ENGLISH_AUTO_LANGUAGE_POLICY
        with self.assertRaises(ValueError): _segment_requests(plan, plan["workload"][0], self.teacher)

    def test_v2_requires_separate_output_preserves_old_checkpoint_and_waveform(self):
        old = self.fixture.narrate(self.runtime)
        old_files = {p: p.read_bytes() for p in self.fixture.output.glob("*.json")}
        old_audio = {p: p.read_bytes() for p in (self.fixture.store / "synthetic-room/audio").glob("*.wav")}
        with self.assertRaisesRegex(ValueError, "distinct_audit_directory"): self.narrate()
        self.fixture.output = self.fixture.root / "audio-audit-english-auto-v1"
        result = self.narrate()
        self.assertTrue(result["allSegmentsPassed"])
        self.assertRegex(result["segments"][0]["ttsRequestId"], r"^tbbtts2_")
        self.assertRegex(result["segments"][0]["asrRequestId"], r"^tbbasr2_")
        for p, data in {**old_files, **old_audio}.items(): self.assertEqual(p.read_bytes(), data)
        self.assertNotEqual(old["segments"][0]["audioUrl"], result["segments"][0]["audioUrl"])
        before = self.runtime.start_formal_audio_tts.call_count
        self.narrate()
        self.assertEqual(self.runtime.start_formal_audio_tts.call_count, before)

    def test_existing_legacy_plan_in_custom_directory_is_never_reinterpreted(self):
        self.fixture.output = self.fixture.root / "other-legacy-audit"
        self.fixture.narrate(self.runtime)
        before = {p: p.read_bytes() for p in self.fixture.output.glob("*.json")}
        count = self.runtime.start_formal_audio_tts.call_count
        with self.assertRaisesRegex(RuntimeError, "frozen_audio_plan_changed"): self.narrate()
        for p, data in before.items(): self.assertEqual(p.read_bytes(), data)
        self.assertEqual(self.runtime.start_formal_audio_tts.call_count, count)

    def test_low_asr_still_stops_at_8500_without_automatic_retry(self):
        self.fixture.output = self.fixture.root / "audio-audit-english-auto-v1"
        transcript = "Unrelated speech."
        self.runtime.start_formal_audio_asr.side_effect = lambda **payload: {
            "requestId": payload["request_id"], "status": "succeeded", "transcript": transcript,
            "transcriptSha256": hashlib.sha256(transcript.encode()).hexdigest(), "completionUsable": True}
        with self.assertRaisesRegex(RuntimeError, "narration_asr_semantic_review_required_no_retry"): self.narrate()
        self.runtime.start_formal_audio_tts.assert_called_once()
        self.runtime.start_formal_audio_asr.assert_called_once()
        self.runtime.save_preview_classroom.assert_not_called()

    def test_v2_unknown_dispatch_is_only_queried_then_stops(self):
        self.fixture.output = self.fixture.root / "audio-audit-english-auto-v1"
        self.runtime.start_formal_audio_tts.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError): self.narrate()
        self.runtime.get_formal_audio_tts.side_effect = audio_fixture.missing()
        with self.assertRaisesRegex(RuntimeError, "audio_prior_dispatch_unresolved_no_retry"): self.narrate()
        self.runtime.start_formal_audio_tts.assert_called_once()

    def test_cli_missing_distinct_output_stops_before_configuration_or_network(self):
        for argv in [[], ["--output", "/candidate/audio-audit"]]:
            with patch("scripts.narrate_textbook_batch.load_candidate", return_value=(
                    {"binding": {"subject": "english"}}, {}, {})), patch("core.config.AppConfig.from_env") as config:
                code = main(["--candidate-directory", "/candidate", "--audio-language-policy",
                             ENGLISH_AUTO_LANGUAGE_OPTION] + argv)
                self.assertEqual(code, 1)
                config.assert_not_called()

    def test_client_namespace_fails_closed_without_adding_request_fields(self):
        validate = OpenMaicFullRuntimeClient._validate_textbook_audio_namespace
        tts = {"subject": "english", "requestId": "tbbtts2_" + "a" * 64}
        validate(tts, "tts")
        asr = {"subject": "english", "requestId": "tbbasr2_" + "b" * 64,
               "ttsRequestId": tts["requestId"]}
        validate(asr, "asr")
        for payload, operation in [({**tts, "subject": "math"}, "tts"),
                ({**tts, "requestId": "tbbtts2_bad"}, "tts"),
                ({**asr, "ttsRequestId": "tbbtts_" + "a" * 64}, "asr"),
                ({**asr, "requestId": "tbbasr_" + "b" * 64}, "asr")]:
            with self.assertRaises(OpenMaicFullRuntimeError): validate(payload, operation)

    def test_client_requires_actual_native_policy_receipt_instead_of_trusting_new_prefix(self):
        request = "tbbtts2_" + "a" * 64
        response = {"success": True, "state": "succeeded", "requestId": request,
                    "audioSha256": "b" * 64, "mimeType": "audio/wav"}
        validate = OpenMaicFullRuntimeClient._validate_formal_tts_response
        with self.assertRaisesRegex(OpenMaicFullRuntimeError, "英语批量语音策略回执不一致"):
            validate(response, request_id=request)
        profile = {"policyVersion": ENGLISH_AUTO_LANGUAGE_POLICY["policyVersion"],
            "policySha256": ENGLISH_AUTO_LANGUAGE_POLICY_SHA256, "providerBodySha256": "c" * 64}
        receipt = validate({**response, "providerLanguagePolicy": profile}, request_id=request)
        self.assertEqual(receipt["providerLanguagePolicy"], profile)
        for mutation in [{"policySha256": "f" * 64}, {"providerBodySha256": "invalid"}, {"unexpected": True}]:
            with self.assertRaises(OpenMaicFullRuntimeError):
                validate({**response, "providerLanguagePolicy": {**profile, **mutation}}, request_id=request)
        legacy = {**response, "requestId": "tbbtts_" + "a" * 64}
        self.assertNotIn("providerLanguagePolicy", validate(legacy, request_id=legacy["requestId"]))

    def test_v2_output_cannot_consume_unknown_existing_files(self):
        self.fixture.output = self.fixture.root / "unknown-audit"
        self.fixture.output.mkdir()
        unknown = self.fixture.output / "audit.json"
        unknown.write_bytes(b"unknown prior operator data")
        with self.assertRaisesRegex(ValueError, "empty_or_matching_audit_directory"): self.narrate()
        self.assertEqual(unknown.read_bytes(), b"unknown prior operator data")
        self.runtime.start_formal_audio_tts.assert_not_called()


if __name__ == "__main__": unittest.main()
