"""Private aliases preserve evidence and never overwrite unknown editor work."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from content.textbook_batch_generation import INPUT_SCHEMA
from content.textbook_catalog import digest
from content.textbook_interactive_narration import bind_interactive_audio
from content.textbook_pedagogy import teaching_profile
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from scripts.private_textbook_preview_snapshot import (load_snapshot, main, persisted_content,
    prepare_snapshot, save_snapshot)
from services.textbook_batch_audio import build_audio_plan, narration_workload
from tests.test_textbook_batch import manifest
from tests.test_textbook_interactive_narration import activity


class PrivatePreviewSnapshotTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.candidate = self.root / ("a" * 64)
        self.candidate.mkdir()
        self.media = self.root / "classrooms"
        self.audio = self.candidate / "audio-audit"
        self.audio.mkdir()
        self.output = self.root / "private-acceptance-snapshot"
        self.original = {"id": "synthetic-source", "createdAt": "source-time", "stage": {"id": "synthetic-source"},
            "scenes": [{"id": "scene-1", "stageId": "synthetic-source", "type": "slide", "order": 0,
                "actions": [{"id": "speech-1", "type": "speech", "text": "看看小猫。"}]},
                {"id": "scene-2", "stageId": "synthetic-source", "type": "interactive", "order": 1, "actions": [],
                    "content": {"html": activity()}}]}
        book = manifest()
        self.binding = {key: book[key] for key in ("editionId", "revisionId", "gradeCode", "subject", "schoolSystem", "volume")}
        frozen = {"schemaVersion": INPUT_SCHEMA, "taskId": self.candidate.name, "binding": self.binding,
            "kind": "book_exploration", "manifest": book, "manifestSha256": digest(book),
            "teachingProfile": teaching_profile("primary_1"), "publicationAllowed": False, "studentDeliveryAllowed": False}
        frozen["inputSha256"] = digest(frozen)
        state = {"schemaVersion": "mira.textbook.private-batch-generation-state.v1", "taskId": self.candidate.name,
            "inputSha256": frozen["inputSha256"], "status": "generated_needs_review", "publicationAllowed": False,
            "studentDeliveryAllowed": False, "classroomId": self.original["id"], "classroomSha256": digest(self.original),
            "runtimeOrigin": "http://127.0.0.1:3100"}
        for name, value in (("input.json", frozen), ("state.json", state), ("classroom.json", self.original)):
            self.write(self.candidate / name, value)
        self.plan = build_audio_plan(self.original, self.binding, state["runtimeOrigin"])
        self.narrated = deepcopy(self.original)
        segments, cue_urls = [], {}
        for index, item in enumerate(narration_workload(self.original)):
            tts = "tbbtts_" + digest({"index": index})
            raw = b"synthetic isolated audio bytes " + bytes([index])
            sha = hashlib.sha256(raw).hexdigest()
            target = self.media / self.original["id"] / "audio" / (tts + ".wav")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            url = f"/api/classroom-media/{self.original['id']}/audio/{tts}.wav"
            segments.append({"sceneId": item["sceneId"], "segmentId": item["id"],
                "textSha256": hashlib.sha256(item["text"].encode()).hexdigest(), "ttsRequestId": tts,
                "asrRequestId": "tbbasr_" + digest({"tts": tts}), "audioSha256": sha, "audioUrl": url,
                "similarityBps": 10000})
            if item["kind"] == "speech":
                self.narrated["scenes"][0]["actions"][0].update(audioId=tts, audioUrl=url,
                    audioMetadata={"schemaVersion": "mira.openmaic.speech-audio.v1",
                        "providerId": self.plan["teacher"]["tts"]["providerId"],
                        "modelId": self.plan["teacher"]["tts"]["modelId"],
                        "voiceId": self.plan["teacher"]["voiceId"], "fallbackUsed": False})
            else:
                cue_urls[item["cueId"]] = url
        self.narrated["scenes"][1]["content"]["html"] = bind_interactive_audio(
            self.original["scenes"][1]["content"]["html"], cue_urls, self.original["id"])
        self.audit = {"schemaVersion": "mira.textbook.batch-audio-audit.v1", "planSha256": digest(self.plan),
            "expectedSegments": len(segments), "completedSegments": len(segments), "segments": segments,
            "allSegmentsPassed": True, "semanticPronunciationReview": "pending", "interactiveStateNarrationReview": "pending",
            "publicationAllowed": False}
        self.audit["sha256"] = digest(self.audit)
        self.write(self.audio / "plan.json", self.plan)
        self.write(self.audio / "audit.json", self.audit)
        self.write(self.audio / "narrated-classroom.json", self.narrated)
        self.before = {p: p.read_bytes() for p in self.candidate.rglob("*.json")}

    @staticmethod
    def write(path, value):
        Path(path).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def prepare(self):
        return prepare_snapshot(self.candidate, self.output, classroom_directory=self.media,
                                alias_id="tbprivate_synthetic_acceptance")

    def runtime(self, existing=None):
        runtime = Mock()
        runtime.base_url = "http://127.0.0.1:3100"
        runtime.rooms = {self.original["id"]: deepcopy(self.narrated)}
        if existing:
            runtime.rooms[existing["id"]] = deepcopy(existing)
        def get(room_id):
            if room_id not in runtime.rooms:
                raise OpenMaicFullRuntimeError("missing", "missing", status_code=404)
            return deepcopy(runtime.rooms[room_id])
        def save(value):
            runtime.rooms[value["id"]] = {**deepcopy(value), "createdAt": "normalized-api-time"}
        runtime.get_classroom.side_effect = get
        runtime.save_preview_classroom.side_effect = save
        return runtime

    def test_prepare_is_offline_preserves_source_html_and_audio_with_new_scene_ids(self):
        with patch("scripts.private_textbook_preview_snapshot.OpenMaicFullRuntimeClient") as client:
            manifest = self.prepare()
        client.assert_not_called()
        _, checked, alias = load_snapshot(self.output)
        self.assertEqual(checked, manifest)
        self.assertNotEqual(alias["id"], self.narrated["id"])
        self.assertEqual(alias["stage"]["id"], alias["id"])
        self.assertFalse(set(s["id"] for s in alias["scenes"]) & set(s["id"] for s in self.original["scenes"]))
        self.assertEqual(alias["scenes"][1]["content"]["html"], self.narrated["scenes"][1]["content"]["html"])
        self.assertEqual(alias["scenes"][0]["actions"], self.narrated["scenes"][0]["actions"])
        self.assertFalse(manifest["publicationAllowed"])
        self.assertEqual(manifest["semanticPronunciationReview"], "pending")
        self.assertTrue(all(p.read_bytes() == raw for p, raw in self.before.items()))

    def test_incomplete_audio_or_wrong_file_stops_without_preparation(self):
        self.audit["allSegmentsPassed"] = False
        self.audit["sha256"] = digest({k: v for k, v in self.audit.items() if k != "sha256"})
        self.write(self.audio / "audit.json", self.audit)
        with self.assertRaisesRegex(ValueError, "complete_audio_audit_required"):
            self.prepare()
        self.assertFalse(self.output.exists())
        self.audit["allSegmentsPassed"] = True
        self.audit["sha256"] = digest({k: v for k, v in self.audit.items() if k != "sha256"})
        self.write(self.audio / "audit.json", self.audit)
        next(self.media.rglob("*.wav")).write_bytes(b"edited")
        with self.assertRaisesRegex(ValueError, "source_audio_changed"):
            self.prepare()

    def test_save_verifies_source_then_posts_only_new_alias_and_reads_back(self):
        manifest = self.prepare()
        runtime = self.runtime()
        result = save_snapshot(self.output, runtime, expected_runtime_core_sha256=manifest["expectedRuntimeCoreSha256"])
        self.assertEqual(result["status"], "saved_private_preview")
        runtime.save_preview_classroom.assert_called_once()
        self.assertEqual(runtime.save_preview_classroom.call_args.args[0]["id"], manifest["aliasClassroomId"])
        self.assertEqual(runtime.rooms[self.original["id"]], self.narrated)
        self.assertEqual(result["readbackPersistedSha256"], manifest["aliasPersistedSha256"])
        self.assertTrue(all(p.read_bytes() == raw for p, raw in self.before.items()))

    def test_known_exact_alias_is_read_only_and_unknown_alias_never_overwritten(self):
        self.prepare()
        _, _, alias = load_snapshot(self.output)
        exact = self.runtime(alias)
        self.assertEqual(save_snapshot(self.output, exact)["status"], "existing_exact_preview_reconciled")
        exact.save_preview_classroom.assert_not_called()
        changed = deepcopy(alias)
        changed["scenes"][0]["actions"][0]["text"] = "operator unsaved work persisted independently"
        unknown = self.runtime(changed)
        with self.assertRaisesRegex(ValueError, "unknown_content"):
            save_snapshot(self.output, unknown)
        unknown.save_preview_classroom.assert_not_called()

    def test_runtime_core_or_audio_binding_drift_blocks_save(self):
        self.prepare()
        for field in ("text", "audioUrl"):
            runtime = self.runtime()
            runtime.rooms[self.original["id"]]["scenes"][0]["actions"][0][field] = "independent runtime edit"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "runtime_source_changed"):
                save_snapshot(self.output, runtime)
            runtime.save_preview_classroom.assert_not_called()

    def test_changed_local_source_or_asset_blocks_before_network(self):
        self.prepare()
        asset = next(self.media.rglob("*.wav"))
        asset.write_bytes(b"changed after prepare")
        runtime = self.runtime()
        with self.assertRaisesRegex(ValueError, "source_audio_changed"):
            save_snapshot(self.output, runtime)
        runtime.get_classroom.assert_not_called()

    def test_lost_save_response_reconciles_existing_exact_alias_without_repost(self):
        self.prepare()
        runtime = self.runtime()
        original_save = runtime.save_preview_classroom.side_effect
        def lost_response(value):
            original_save(value)
            raise OpenMaicFullRuntimeError("timeout", "timeout", status_code=503)
        runtime.save_preview_classroom.side_effect = lost_response
        with self.assertRaises(OpenMaicFullRuntimeError):
            save_snapshot(self.output, runtime)
        result = save_snapshot(self.output, runtime)
        self.assertEqual(result["status"], "existing_exact_preview_reconciled")
        self.assertEqual(runtime.save_preview_classroom.call_count, 1)

    def test_ambiguous_save_missing_alias_is_not_automatically_reposted(self):
        self.prepare()
        runtime = self.runtime()
        runtime.save_preview_classroom.side_effect = OpenMaicFullRuntimeError("timeout", "timeout", status_code=503)
        with self.assertRaises(OpenMaicFullRuntimeError):
            save_snapshot(self.output, runtime)
        with self.assertRaisesRegex(RuntimeError, "missing_no_repost"):
            save_snapshot(self.output, runtime)
        self.assertEqual(runtime.save_preview_classroom.call_count, 1)

    def test_unknown_get_failure_and_remote_origin_stop_without_post(self):
        self.prepare()
        runtime = self.runtime()
        runtime.get_classroom.side_effect = OpenMaicFullRuntimeError("unavailable", "unavailable", status_code=503)
        with self.assertRaises(OpenMaicFullRuntimeError):
            save_snapshot(self.output, runtime)
        runtime.save_preview_classroom.assert_not_called()
        remote = self.runtime()
        remote.base_url = "https://example.org"
        with self.assertRaisesRegex(ValueError, "local_runtime_required"):
            save_snapshot(self.output, remote)
        remote.get_classroom.assert_not_called()

    def test_snapshot_integrity_and_expected_runtime_hash_are_required(self):
        self.prepare()
        runtime = self.runtime()
        with self.assertRaisesRegex(ValueError, "expected_runtime_identity_mismatch"):
            save_snapshot(self.output, runtime, expected_runtime_core_sha256="0" * 64)
        runtime.get_classroom.assert_not_called()
        alias_file = self.output / "classroom.json"
        alias = json.loads(alias_file.read_text())
        alias["scenes"][0]["actions"][0]["audioUrl"] = "/changed.wav"
        self.write(alias_file, alias)
        with self.assertRaisesRegex(ValueError, "snapshot_integrity_failed"):
            load_snapshot(self.output)


if __name__ == "__main__":
    unittest.main()
