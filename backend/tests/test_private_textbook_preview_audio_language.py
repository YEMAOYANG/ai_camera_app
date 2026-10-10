"""Private preview consumes saved v2 policy without silently migrating v1."""
from copy import deepcopy
import json
import unittest

from content.textbook_catalog import digest
from content.textbook_interactive_narration import bind_interactive_audio, without_audio_helper
from services.textbook_batch_audio import (ENGLISH_AUTO_LANGUAGE_OPTION, _asr_request_id,
    _segment_requests, build_audio_plan, narration_workload)
from content.teacher_profiles import get_formal_subject_qwen_voice_identity
from tests import test_private_textbook_preview_snapshot as fixture


class PreviewEnglishAutoPlanTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture.PrivatePreviewSnapshotTest()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def prepare_v2(self):
        f = self.f
        frozen = json.loads((f.candidate / "input.json").read_text())
        state = json.loads((f.candidate / "state.json").read_text())
        f.binding["subject"] = "english"
        frozen["binding"] = f.binding
        frozen["manifest"]["subject"] = "english"
        frozen["manifestSha256"] = digest(frozen["manifest"])
        frozen["inputSha256"] = digest({k: v for k, v in frozen.items() if k != "inputSha256"})
        state["inputSha256"] = frozen["inputSha256"]
        f.write(f.candidate / "input.json", frozen)
        f.write(f.candidate / "state.json", state)
        f.plan = build_audio_plan(f.original, f.binding, state["runtimeOrigin"],
                                 audio_language_policy=ENGLISH_AUTO_LANGUAGE_OPTION)
        teacher = get_formal_subject_qwen_voice_identity("english")
        cue_urls = {}
        for item, segment in zip(narration_workload(f.original), f.audit["segments"]):
            old_id = segment["ttsRequestId"]
            tts, _, _, _ = _segment_requests(f.plan, item, teacher)
            audio_root = f.media / f.original["id"] / "audio"
            (audio_root / (tts + ".wav")).write_bytes((audio_root / (old_id + ".wav")).read_bytes())
            url = f"/api/classroom-media/{f.original['id']}/audio/{tts}.wav"
            segment.update(ttsRequestId=tts, asrRequestId=_asr_request_id(f.plan, tts, segment["audioSha256"]), audioUrl=url)
            if item["kind"] == "speech":
                f.narrated["scenes"][0]["actions"][0].update(audioId=tts, audioUrl=url,
                    audioMetadata={"schemaVersion": "mira.openmaic.speech-audio.v1", "providerId": "qwen-tts",
                        "modelId": "qwen3-tts-flash", "voiceId": "Jennifer", "fallbackUsed": False})
            else:
                cue_urls[item["cueId"]] = url
        f.narrated["scenes"][1]["content"]["html"] = bind_interactive_audio(
            without_audio_helper(f.narrated["scenes"][1]["content"]["html"]), cue_urls, f.original["id"])
        f.audit["planSha256"] = digest(f.plan)
        self.persist()

    def persist(self):
        f = self.f
        f.audit["sha256"] = digest({k: v for k, v in f.audit.items() if k != "sha256"})
        f.write(f.audio / "plan.json", f.plan)
        f.write(f.audio / "audit.json", f.audit)
        f.write(f.audio / "narrated-classroom.json", f.narrated)

    def test_saved_v2_exact_policy_and_audio_namespace_can_prepare_preview(self):
        self.prepare_v2()
        before = {p: p.read_bytes() for p in self.f.candidate.rglob("*.json")}
        result = self.f.prepare()
        self.assertEqual(result["audioPlanSha256"], digest(self.f.plan))
        self.assertFalse(result["audioUrlsRewritten"])
        self.assertFalse(result["publicationAllowed"])
        for p, data in before.items(): self.assertEqual(p.read_bytes(), data)

    def test_tampered_policy_or_legacy_namespace_is_rejected(self):
        self.prepare_v2()
        original_plan = deepcopy(self.f.plan)
        self.f.plan["providerLanguagePolicy"]["asr"]["automaticLanguage"] = False
        self.persist()
        with self.assertRaisesRegex(ValueError, "invalid_textbook_audio_language_policy"): self.f.prepare()
        self.assertFalse(self.f.output.exists())
        self.f.plan = original_plan
        self.f.audit["segments"][0]["ttsRequestId"] = "tbbtts_" + "a" * 64
        self.persist()
        with self.assertRaisesRegex(ValueError, "audio_language_namespace_mismatch"): self.f.prepare()
        self.assertFalse(self.f.output.exists())

    def test_legacy_plan_is_not_upgraded_from_subject_alone(self):
        result = self.f.prepare()
        self.assertEqual(result["audioPlanSha256"], digest(self.f.plan))
        self.assertEqual(self.f.plan["schemaVersion"], "mira.textbook.batch-audio.v1")
        self.assertNotIn("providerLanguagePolicy", self.f.plan)


if __name__ == "__main__": unittest.main()
