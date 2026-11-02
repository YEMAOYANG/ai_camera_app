"""Garden 4 probe runner tests; every provider and download is synthetic."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import wave

from content import textbook_pinyin_pronunciation as pronunciation
from content.textbook_catalog import canonical, digest
from content.textbook_pinyin_operator_review import AUTHORIZATION_SCHEMA
from core.errors import ApiError
from scripts import generate_textbook_pronunciation_probe as cli
from services import textbook_preview_pronunciation_initialization as initialization
from services import textbook_pronunciation_probe_generation as generation


LESSON = {
    "editionId": "pep-chinese-g1-upper-2022-standard",
    "revisionId": "20260924-directory-3",
    "nodeId": "u4-l6",
    "gradeCode": "primary_1",
    "subject": "chinese",
    "teachingRevision": "teaching-1",
}


def seal(value):
    value["sha256"] = digest({key: item for key, item in value.items() if key != "sha256"})
    return value


def wav_fixture(*, streaming=True):
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\0\1" * 2400)
    raw = bytearray(output.getvalue())
    if streaming:
        struct.pack_into("<I", raw, 4, 0x7FFFFFBF)
        struct.pack_into("<I", raw, 40, 0x7FFFFF9B)
    return bytes(raw)


class FakeTransport:
    endpoint = "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer"

    def __init__(self, audio=None, *, post_error=None, download_error=None, start_ordinal=0,
                 fixed_request_id=None):
        self.audio = audio or wav_fixture()
        self.post_error = post_error
        self.download_error = download_error
        self.start_ordinal = start_ordinal
        self.fixed_request_id = fixed_request_id
        self.posts = []
        self.downloads = []

    def post(self, request_bytes):
        self.posts.append(request_bytes)
        if self.post_error:
            raise self.post_error
        ordinal = self.start_ordinal + len(self.posts)
        request_id = self.fixed_request_id or f"0000000{ordinal}-0000-0000-0000-00000000000{ordinal}"
        response = {
            "request_id": request_id,
            "output": {"finish_reason": "stop", "audio": {"data": "", "id": "audio_" + request_id, "url": (
                "http://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/"
                f"prod/cosyvoice-v3-flash/20261027/12345/{request_id}.wav?Expires=1&Signature=test")}},
            "usage": {"characters": 10 + ordinal},
        }
        return generation.json_bytes(response)

    def download(self, media_url, *, model):
        self.downloads.append((media_url, model))
        if self.download_error:
            raise self.download_error
        return self.audio


class ProbeGenerationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "garden4-probes"
        self.auth = Path(temporary.name) / "dispatch-authorization.json"
        self.review_context = Path(temporary.name) / "review-context.json"
        self.prepared = generation.prepare(self.root, LESSON)
        self.plan_raw = (self.root / "plan.json").read_bytes()
        self.plan = json.loads(self.plan_raw)
        self.plan_sha = generation.sha_bytes(self.plan_raw)
        authorization = seal({
            "schemaVersion": generation.DISPATCH_AUTHORIZATION_SCHEMA,
            "source": "user-message",
            "statement": "Synthetic test authorization for exactly four mocked calls; no network.",
            "recordedAt": 100,
            "sourceLesson": LESSON,
            "policyVersion": pronunciation.GARDEN4_POLICY_VERSION,
            "planSha256": self.plan_sha,
            "provider": self.plan["provider"],
            "plannedCalls": 4,
            "paidProviderCallsAuthorized": True,
            "maximumPostAttemptsPerSample": 1,
            "formalUseAllowed": False,
        })
        self.auth.write_text(canonical(authorization), encoding="utf-8")

    def _run(self, transport):
        return generation.run(self.root, self.auth, transport=transport, now_ms=200)

    def _write_review_context(self):
        operator_authorization = seal({
            "schemaVersion": AUTHORIZATION_SCHEMA,
            "source": "user-message",
            "statement": "Synthetic automated protocol checks only; not human listening.",
            "recordedAt": 100,
            "scope": {key: LESSON[key] for key in ("editionId", "gradeCode", "subject")},
            "automatedChecksAuthorized": True,
            "publicationAuthorized": True,
            "individualListeningConfirmationRequired": False,
        })
        context = {
            "schemaVersion": generation.REVIEW_CONTEXT_SCHEMA,
            "previewKey": "preview-fixture",
            "sourceSha256": "a" * 64,
            "coreSha256": "b" * 64,
            "reviewer": "synthetic-operator",
            "recordedAt": 200,
            "authorization": operator_authorization,
        }
        self.review_context.write_text(canonical(context), encoding="utf-8")
        return context

    def test_prepare_uses_only_registered_four_sample_contract_and_zero_provider_calls(self):
        self.assertEqual(self.prepared, {"prepared": True, "planSha256": self.plan_sha,
            "plannedCalls": 4, "providerCalls": 0, "formalUseAllowed": False})
        policy = pronunciation.registered_policy(pronunciation.GARDEN4_POLICY_VERSION)
        self.assertEqual(self.plan["plannedCalls"], 4)
        self.assertEqual((self.plan["provider"], self.plan["model"], self.plan["voice"]),
                         (policy["providerId"], policy["modelId"], policy["voiceId"]))
        self.assertEqual([sample["label"] for sample in self.plan["samples"]],
                         list(initialization._GARDEN4_PROBE_TEXTS))
        for sample in self.plan["samples"]:
            expected = pronunciation.provider_body(
                initialization._GARDEN4_PROBE_TEXTS[sample["label"]],
                policy_version=pronunciation.GARDEN4_POLICY_VERSION)
            self.assertEqual(sample["body"], expected)
            self.assertEqual((self.root / sample["label"] / "request.json").read_bytes(),
                             generation.json_bytes(expected))
            self.assertEqual({path.name for path in (self.root / sample["label"]).iterdir()}, {"request.json"})

    def test_run_persists_each_intent_before_exactly_four_posts_and_writes_complete_evidence(self):
        transport = FakeTransport()
        original_post = transport.post

        def assert_intent_first(request_bytes):
            sample = self.plan["samples"][len(transport.posts)]
            self.assertTrue((self.root / sample["label"] / "intent.json").is_file())
            self.assertFalse((self.root / sample["label"] / "receipt.json").exists())
            return original_post(request_bytes)

        transport.post = assert_intent_first
        result = self._run(transport)
        self.assertTrue(result["completed"])
        self.assertEqual(len(transport.posts), 4)
        self.assertEqual(len(transport.downloads), 4)
        for sample in self.plan["samples"]:
            folder = self.root / sample["label"]
            self.assertEqual({path.name for path in folder.iterdir()}, set(generation.PROBE_FILES))
            receipt = generation.verify_completed_sample(self.root, self.plan, sample, self.plan_sha)
            self.assertEqual(receipt["postAttempts"], 1)
            self.assertFalse(receipt["humanListeningVerified"])
            self.assertNotEqual((folder / "audio.wav").read_bytes(), (folder / "playback.wav").read_bytes())
            self.assertEqual((folder / "audio.wav").read_bytes()[44:],
                             (folder / "playback.wav").read_bytes()[44:])
        replay = FakeTransport()
        self.assertTrue(self._run(replay)["completed"])
        self.assertEqual(replay.posts, [])
        self.assertEqual(replay.downloads, [])

    def test_unknown_post_stops_first_label_and_never_reposts_existing_intent(self):
        first = FakeTransport(post_error=generation.ProviderOutcomeUnknown(
            "provider_outcome_unknown", "synthetic unknown; do not retry"))
        with self.assertRaises(generation.ProviderOutcomeUnknown):
            self._run(first)
        self.assertEqual(len(first.posts), 1)
        label = self.plan["samples"][0]["label"]
        receipt = json.loads((self.root / label / "receipt.json").read_text())
        self.assertEqual(receipt["status"], "unknown")
        second = FakeTransport()
        with self.assertRaisesRegex(generation.PronunciationProbeError, "do not retry"):
            self._run(second)
        self.assertEqual(second.posts, [])
        self.assertFalse((self.root / self.plan["samples"][1]["label"] / "intent.json").exists())

    def test_saved_success_response_allows_download_only_recovery_without_reposting_that_label(self):
        first = FakeTransport(download_error=generation.PronunciationProbeError(
            "audio_download_unknown", "synthetic download failure"))
        with self.assertRaisesRegex(generation.PronunciationProbeError, "download failure"):
            self._run(first)
        self.assertEqual(len(first.posts), 1)
        first_request = first.posts[0]
        label = self.plan["samples"][0]["label"]
        self.assertTrue((self.root / label / "provider-response.json").is_file())
        self.assertFalse((self.root / label / "receipt.json").exists())
        recovery = FakeTransport(start_ordinal=1)
        result = self._run(recovery)
        self.assertTrue(result["completed"])
        self.assertEqual(len(recovery.posts), 3)
        self.assertNotIn(first_request, recovery.posts)
        self.assertEqual(len(recovery.downloads), 4)

    def test_reused_request_identity_is_rejected_before_audio_and_review(self):
        duplicate = "00000001-0000-0000-0000-000000000001"
        transport = FakeTransport(fixed_request_id=duplicate)
        with self.assertRaisesRegex(generation.PronunciationProbeError, "reused"):
            self._run(transport)
        self.assertEqual(len(transport.posts), 2)
        second = self.root / self.plan["samples"][1]["label"]
        self.assertTrue((second / "provider-response.json").is_file())
        self.assertFalse((second / "audio.wav").exists())
        self.assertFalse((second / "receipt.json").exists())

    def test_response_request_audio_and_url_identities_must_match(self):
        sample = self.plan["samples"][0]
        request_id = "00000001-0000-0000-0000-000000000001"
        good = {
            "request_id": request_id,
            "output": {"finish_reason": "stop", "audio": {"id": "audio_" + request_id,
                "url": ("https://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/prod/"
                        "cosyvoice-v3-flash/20261027/1/" + request_id + ".wav?sig=1")}},
            "usage": {"characters": 1},
        }
        for changed in ("audio-id", "url-id"):
            value = deepcopy(good)
            if changed == "audio-id":
                value["output"]["audio"]["id"] = "audio_00000002-0000-0000-0000-000000000002"
            else:
                value["output"]["audio"]["url"] = value["output"]["audio"]["url"].replace(
                    request_id + ".wav", "00000002-0000-0000-0000-000000000002.wav")
            with self.subTest(changed=changed), self.assertRaises(generation.PronunciationProbeError):
                generation._validated_response(generation.json_bytes(value), model=self.plan["model"])
        self.assertEqual(sample["label"], "near-contrast-and-poem-context")

    def test_tampered_existing_intent_fails_before_download_or_new_artifacts(self):
        first = FakeTransport(download_error=generation.PronunciationProbeError(
            "audio_download_unknown", "synthetic download failure"))
        with self.assertRaises(generation.PronunciationProbeError):
            self._run(first)
        label = self.plan["samples"][0]["label"]
        folder = self.root / label
        intent = json.loads((folder / "intent.json").read_text())
        intent["target"] = "tampered"
        (folder / "intent.json").write_text(canonical(intent))
        recovery = FakeTransport(start_ordinal=1)
        with self.assertRaisesRegex(generation.PronunciationProbeError, "intent"):
            self._run(recovery)
        self.assertEqual(recovery.posts, [])
        self.assertEqual(recovery.downloads, [])
        self.assertFalse((folder / "audio.wav").exists())
        self.assertFalse((folder / "receipt.json").exists())

    def test_invalid_download_is_not_persisted_and_good_get_only_recovery_succeeds(self):
        corrupt = FakeTransport(audio=b"not-a-wav")
        with self.assertRaisesRegex(generation.PronunciationProbeError, "WAV"):
            self._run(corrupt)
        label = self.plan["samples"][0]["label"]
        folder = self.root / label
        self.assertTrue((folder / "provider-response.json").is_file())
        self.assertFalse((folder / "audio.wav").exists())
        recovery = FakeTransport(start_ordinal=1)
        self.assertTrue(self._run(recovery)["completed"])
        self.assertEqual(len(recovery.posts), 3)

    def test_definitive_failure_receipt_is_terminal(self):
        rejected = FakeTransport(post_error=generation.ProviderRejected(400, "c" * 64))
        with self.assertRaises(generation.ProviderRejected):
            self._run(rejected)
        replay = FakeTransport()
        with self.assertRaisesRegex(generation.PronunciationProbeError, "do not retry"):
            self._run(replay)
        self.assertEqual(replay.posts, [])

    def test_later_terminal_state_is_preflighted_before_any_earlier_post(self):
        authorization = json.loads(self.auth.read_text())
        sample = self.plan["samples"][2]
        folder = self.root / sample["label"]
        intent = generation._intent(sample, self.plan, self.plan_sha, authorization["sha256"],
            endpoint=FakeTransport.endpoint, created_at="2026-10-27T00:00:00Z")
        (folder / "intent.json").write_text(canonical(intent))
        receipt = generation._terminal_receipt(sample, self.plan, self.plan_sha, authorization["sha256"],
            status="unknown", reason_code="provider_outcome_unknown")
        (folder / "receipt.json").write_text(canonical(receipt))
        transport = FakeTransport()
        with self.assertRaisesRegex(generation.PronunciationProbeError, "do not retry"):
            self._run(transport)
        self.assertEqual(transport.posts, [])

    def test_status_does_not_report_tampered_success_as_succeeded(self):
        self._run(FakeTransport())
        first = self.plan["samples"][0]
        (self.root / first["label"] / "audio.wav").unlink()
        row = next(item for item in generation.status(self.root)["samples"]
                   if item["label"] == first["label"])
        self.assertEqual(row["state"], "invalid-evidence")

    def test_review_is_activation_compatible_and_cannot_claim_human_listening(self):
        self._run(FakeTransport())
        context = self._write_review_context()
        review = generation.build_operator_review(self.root, self.review_context, now_ms=300)
        self.assertFalse(review["humanListeningVerified"])
        self.assertFalse(review["perceptualToneVerified"])
        self.assertFalse(review["formalUseAllowed"])
        self.assertEqual(review["result"], initialization.OPERATOR_RESULT)
        self.assertEqual(len(review["samples"]), 4)
        self.assertEqual((self.root / "operator-probe-review.json").read_bytes(), generation.json_bytes(review))

        policy = pronunciation.registered_policy(pronunciation.GARDEN4_POLICY_VERSION)
        patch_value = {
            "schemaVersion": initialization.OPERATOR_SCHEMA,
            "expectedSourceSha256": context["sourceSha256"],
            "expectedCoreSha256": context["coreSha256"],
            "pronunciationPolicyVersion": policy["policyVersion"],
            "pronunciationPolicySha256": digest(policy),
            "reviewer": context["reviewer"],
            "basis": "Synthetic protocol and WAV validation only.",
            "verifiedProbeEvidence": {
                "path": str(self.root / "operator-probe-review.json"),
                "sha256": generation.sha_bytes(generation.json_bytes(review)),
            },
        }
        files = {"evidence/operator-probe-review.json": generation.json_bytes(review),
                 "evidence/plan.json": self.plan_raw}
        for sample in self.plan["samples"]:
            for name in generation.PROBE_FILES:
                files[f"evidence/{sample['label']}/{name}"] = (self.root / sample["label"] / name).read_bytes()
        initialization._verify_evidence(files, patch_value, context["previewKey"],
                                        generation._binding(LESSON), policy)

    def test_wrong_lesson_and_tampered_authorization_fail_before_provider(self):
        with self.assertRaises(generation.PronunciationProbeError):
            generation.build_plan({**LESSON, "nodeId": "u4-l5"})
        authorization = json.loads(self.auth.read_text())
        authorization["plannedCalls"] = 5
        self.auth.write_text(canonical(authorization))
        transport = FakeTransport()
        with self.assertRaisesRegex(generation.PronunciationProbeError, "authorization"):
            self._run(transport)
        self.assertEqual(transport.posts, [])

    def test_prepare_cli_does_not_resolve_credentials_or_construct_transport(self):
        other = self.root.parent / "cli-probes"
        args = ["prepare", "--output-dir", str(other), "--edition-id", LESSON["editionId"],
                "--alignment-revision-id", LESSON["revisionId"], "--node-id", LESSON["nodeId"],
                "--grade-code", LESSON["gradeCode"], "--subject", LESSON["subject"],
                "--teaching-revision", LESSON["teachingRevision"]]
        with patch.object(generation.AliyunCosyVoiceProbeTransport, "from_environment",
                          side_effect=AssertionError("prepare must not resolve a key")), redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(args), 0)

    def test_cli_turns_domain_validation_error_into_json_without_traceback(self):
        stderr = io.StringIO()
        with patch.object(cli, "build_operator_review", side_effect=ApiError("fixture_invalid", "bad evidence", 409)), \
                redirect_stderr(stderr), redirect_stdout(io.StringIO()):
            result = cli.main(["review", "--output-dir", str(self.root),
                               "--review-context", str(self.review_context)])
        self.assertEqual(result, 1)
        self.assertEqual(json.loads(stderr.getvalue())["error"], "fixture_invalid")
        self.assertNotIn("Traceback", stderr.getvalue())


class ProbePrimitiveTests(unittest.TestCase):
    def test_media_url_is_upgraded_and_rejects_other_hosts_models_and_paths(self):
        good = ("http://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/prod/cosyvoice-v3-flash/"
                "20261027/123/00000001-0000-0000-0000-000000000001.wav?Expires=1&Signature=x")
        self.assertTrue(generation.validated_media_url(good, model="cosyvoice-v3-flash").startswith("https://"))
        for bad in (good.replace("dashscope-result-bj", "attacker"),
                    good.replace("cosyvoice-v3-flash", "other"),
                    good.replace(".wav?", ".mp3?"), good.split("?")[0]):
            with self.subTest(bad=bad), self.assertRaises(generation.PronunciationProbeError):
                generation.validated_media_url(bad, model="cosyvoice-v3-flash")

    def test_wav_normalization_changes_only_streaming_length_fields(self):
        original = wav_fixture(streaming=True)
        playback, normalization = generation.normalize_wav(original)
        self.assertTrue(normalization["applied"])
        self.assertEqual(original[44:], playback[44:])
        self.assertNotEqual(original[4:8], playback[4:8])
        self.assertNotEqual(original[40:44], playback[40:44])
        changed = [index for index, pair in enumerate(zip(original, playback)) if pair[0] != pair[1]]
        self.assertTrue(set(changed) <= set(range(4, 8)) | set(range(40, 44)))
        ordinary = wav_fixture(streaming=False)
        ordinary_playback, ordinary_normalization = generation.normalize_wav(ordinary)
        self.assertFalse(ordinary_normalization["applied"])
        self.assertEqual(ordinary_playback, ordinary)


if __name__ == "__main__":
    unittest.main()
