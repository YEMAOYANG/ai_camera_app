"""Private aliases preserve evidence and never overwrite unknown editor work."""
from copy import deepcopy
import base64
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

from content.textbook_batch_generation import INPUT_SCHEMA
from content.textbook_catalog import digest
from content.textbook_asr_source_reuse import ORIGIN_SCHEMA, build_audit, formal_request
from content.textbook_interactive_narration import (bind_interactive_audio, interactive_cues,
                                                     without_audio_helper)
from content.textbook_pedagogy import teaching_profile
from content.textbook_preview_audio_contract import (new_audio_plan, new_pinyin_audio_plan,
                                                      revision_audio_plan)
from core.errors import ApiError
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from scripts.private_textbook_preview_snapshot import (load_snapshot, main, persisted_content,
    prepare_snapshot, prepare_pinyin_snapshot, save_snapshot, make_alias, PLAYBACK_CONTRACT,
    LEGACY_FIXED_PLAYBACK_CONTRACT, PINYIN_ORIGIN_SCHEMA, teaching_core,
    verify_pinyin_playback_bindings)
from services.textbook_batch_audio import build_audio_plan, narration_workload
from services.textbook_preview_audio import core_content
from tests.test_textbook_batch import manifest
from tests.test_textbook_interactive_narration import activity
from tests import test_textbook_pinyin_operator_review_v3 as pinyin_v3_fixtures


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
        self.assertIs(alias["stage"]["miraTextbookPreviewNarration"], True)
        self.assertNotIn("fixedTextbook", alias["stage"])
        self.assertEqual(manifest["playbackContract"], PLAYBACK_CONTRACT)
        self.assertNotIn("fixedTextbook", self.narrated["stage"])
        self.assertFalse(set(s["id"] for s in alias["scenes"]) & set(s["id"] for s in self.original["scenes"]))
        self.assertEqual(alias["scenes"][1]["content"]["html"], self.narrated["scenes"][1]["content"]["html"])
        self.assertEqual(alias["scenes"][0]["actions"], self.narrated["scenes"][0]["actions"])
        self.assertFalse(manifest["publicationAllowed"])
        self.assertEqual(manifest["semanticPronunciationReview"], "pending")
        self.assertTrue(all(p.read_bytes() == raw for p, raw in self.before.items()))

    def test_legacy_snapshot_remains_readable_without_silently_changing_playback(self):
        manifest = self.prepare()
        alias, _ = make_alias(self.narrated, manifest["aliasClassroomId"])
        manifest.pop("playbackContract")
        manifest["aliasClassroomSha256"] = digest(alias)
        manifest["aliasPersistedSha256"] = digest(persisted_content(alias))
        manifest["snapshotSha256"] = digest({k: v for k, v in manifest.items() if k != "snapshotSha256"})
        self.write(self.output / "snapshot.json", manifest)
        self.write(self.output / "classroom.json", alias)
        _, checked, loaded = load_snapshot(self.output)
        self.assertNotIn("fixedTextbook", loaded["stage"])
        self.assertNotIn("miraTextbookPreviewNarration", loaded["stage"])
        self.assertNotIn("playbackContract", checked)

    def test_recorded_fixed_preview_remains_exact_and_is_not_silently_replaced(self):
        manifest = self.prepare()
        alias, _ = make_alias(self.narrated, manifest["aliasClassroomId"], fixed_textbook=True)
        manifest["playbackContract"] = LEGACY_FIXED_PLAYBACK_CONTRACT
        manifest["aliasClassroomSha256"] = digest(alias)
        manifest["aliasPersistedSha256"] = digest(persisted_content(alias))
        manifest["snapshotSha256"] = digest({k: v for k, v in manifest.items() if k != "snapshotSha256"})
        self.write(self.output / "snapshot.json", manifest)
        self.write(self.output / "classroom.json", alias)
        _, _, loaded = load_snapshot(self.output)
        self.assertIs(loaded["stage"]["fixedTextbook"], True)
        self.assertNotIn("miraTextbookPreviewNarration", loaded["stage"])
        with self.assertRaisesRegex(ValueError, "playback_contract_invalid"):
            make_alias(loaded, "tbprivate_invalid_mode", narration_preview=True)

    def test_unknown_playback_contract_and_unrecorded_flag_are_rejected(self):
        manifest = self.prepare()
        manifest["playbackContract"] = {**PLAYBACK_CONTRACT, "fixedTextbook": False}
        manifest["snapshotSha256"] = digest({k: v for k, v in manifest.items() if k != "snapshotSha256"})
        self.write(self.output / "snapshot.json", manifest)
        with self.assertRaisesRegex(ValueError, "playback_contract_invalid"):
            load_snapshot(self.output)
        manifest.pop("playbackContract")
        manifest["snapshotSha256"] = digest({k: v for k, v in manifest.items() if k != "snapshotSha256"})
        self.write(self.output / "snapshot.json", manifest)
        with self.assertRaisesRegex(ValueError, "alias_content_changed"):
            load_snapshot(self.output)

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


class PinyinOriginPrivatePreviewSnapshotTest(unittest.TestCase):
    def setUp(self):
        fixture = pinyin_v3_fixtures.AliasOperatorV3Tests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.f = fixture, fixture.f
        self.audio_directory = self.f.root / self.f.cid
        self.classroom_path = self.f.root / (self.f.cid + ".json")
        self.audit_path = self.f.root / "origin-audit.json"
        self.output = self.f.root / "private-pinyin-origin-snapshot"
        # Rebuild the small fixture under one current v3 plan. The two clips
        # deliberately have different PCM identities, like an actual lesson.
        source = deepcopy(self.f.classroom)
        for scene in source["scenes"]:
            for action in scene.get("actions", []):
                for field in ("audioId", "audioUrl", "audioMetadata"):
                    action.pop(field, None)
            for question in scene.get("content", {}).get("questions", []):
                question.pop("questionAudioUrl", None)
        question = source["scenes"][2]["content"]["questions"][0]
        source["scenes"][2]["actions"] = [{"id": "quiz-question-speech", "type": "speech",
                                              "text": question["question"]}]
        core_sha = digest(teaching_core(source))
        args = {"preview_key": self.f.key, "classroom_sha256": digest(source), "core_sha256": core_sha,
                "frozen_input": fixture.frozen}
        parent = new_audio_plan(**args)
        self.f.plan = new_pinyin_audio_plan(**args, parent_plan=parent, revision_id="e" * 64)
        for path in (self.audio_directory / "audio").glob("*.wav"):
            path.unlink()
        fixture.receipts, entries, targets, origins = [], [], [], []
        base_audio = fixture.audio
        speech_scenes = [scene for scene in source["scenes"] if scene.get("actions")]
        for index, scene in enumerate(speech_scenes):
            fixture.audio = base_audio if index == 0 else base_audio[:-2] + bytes([index, 0])
            action = scene["actions"][0]
            receipt = fixture.audio_receipt(scene, action, self.f.plan)
            entry = fixture.audit_entry(scene, action, receipt, action["text"])
            audio = (self.audio_directory / "audio" / (action["audioId"] + ".wav")).read_bytes()
            target = {"sceneId": scene["id"], "sceneOrder": scene.get("order", 0),
                "action": deepcopy(action), "ttsReceipt": deepcopy(receipt), "requestPlan": None,
                "audioBase64": base64.b64encode(audio).decode()}
            response = entry["asr"]
            attempt = {"kind": "formal", "role": "routine", "source": deepcopy(target),
                "plan": deepcopy(self.f.plan), "classroomId": self.f.cid,
                "request": formal_request(target, self.f.plan, self.f.cid, response["requestId"]),
                "response": deepcopy(response)}
            origin = {"schemaVersion": ORIGIN_SCHEMA, "kind": "formal", "source": deepcopy(target),
                "plan": deepcopy(self.f.plan), "classroomId": self.f.cid, "attempts": [attempt]}
            fixture.receipts.append(receipt)
            entries.append(entry)
            targets.append({"target": target, "originSha256": digest(origin)})
            origins.append(origin)
        fixture.audio = base_audio
        source["scenes"][2]["content"]["questions"][0]["questionAudioUrl"] = \
            source["scenes"][2]["actions"][0]["audioUrl"]
        self.f.classroom = source
        self.audit = build_audit(plan=self.f.plan, classroom=source, targets=targets, origins=origins)
        self.source_sha = digest(source)
        self.core_sha = core_sha
        self.plan_sha = digest(self.f.plan)
        self.write(self.classroom_path, source)
        self.write(self.audio_directory / "textbook-preview-audio" / "plan.json", self.f.plan)
        self.write(self.audio_directory / "textbook-preview-audio" / "receipts.json", fixture.receipts)
        self.write(self.audit_path, self.audit)
        self.original_bytes = {path: path.read_bytes() for path in (self.classroom_path,
            self.audio_directory / "textbook-preview-audio" / "plan.json",
            self.audio_directory / "textbook-preview-audio" / "receipts.json", self.audit_path)}

    @staticmethod
    def write(path, value):
        Path(path).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def prepare(self, **changes):
        options = {"expected_source_sha256": self.source_sha, "expected_core_sha256": self.core_sha,
            "expected_plan_sha256": self.plan_sha, "expected_speech_count": 3,
            "runtime_origin": "http://127.0.0.1:3100", "alias_id": "tbprivate_pinyin_origin_fixture"}
        options.update(changes)
        return prepare_pinyin_snapshot(self.classroom_path, self.audio_directory, self.audit_path,
                                       self.output, **options)

    def sequential_revisions(self):
        """Build two committed append-only revisions across a slide and quiz."""
        classroom = deepcopy(self.f.classroom)
        receipts = deepcopy(self.fixture.receipts)
        plans = {}
        base_audio = self.fixture.audio
        identities = [(0, "第一次修订后的讲解。"), (2, "第二次修订后的题目。")]
        for ordinal, (scene_index, replacement) in enumerate(identities, 1):
            revision_id = ("a" if ordinal == 1 else "b") * 64
            archive = self.audio_directory / "textbook-preview-audio" / "narration-revisions" / revision_id
            archive.mkdir(parents=True)
            source = deepcopy(classroom)
            target_text = deepcopy(source)
            scene = target_text["scenes"][scene_index]
            action = scene["actions"][0]
            old_text = action["text"]
            action["text"] = replacement
            if scene.get("type") == "interactive":
                scene["content"]["html"] = scene["content"]["html"].replace(old_text, replacement)
            if scene.get("type") == "quiz":
                question = scene["content"]["questions"][0]
                self.assertEqual(question["question"], old_text)
                question["question"] = replacement
            child = revision_audio_plan(self.f.plan, revision_id=revision_id,
                classroom_sha256=digest(target_text), core_sha256=digest(core_content(target_text)),
                frozen_input=self.fixture.frozen)
            target = deepcopy(target_text)
            target_scene = target["scenes"][scene_index]
            target_action = target_scene["actions"][0]
            self.fixture.audio = base_audio[:-2] + bytes([10 + ordinal, 0])
            receipt = self.fixture.audio_receipt(target_scene, target_action, child)
            self.fixture.audio = base_audio
            if target_scene.get("type") == "interactive":
                html = target_scene["content"]["html"]
                base = without_audio_helper(html)
                clips = {}
                for cue in interactive_cues(base):
                    matches = [item for item in target_scene["actions"]
                               if item.get("type") == "speech" and item.get("text") == cue["text"]]
                    self.assertEqual(len(matches), 1)
                    clips[cue["id"]] = matches[0]["audioUrl"]
                target_scene["content"]["html"] = bind_interactive_audio(base, clips, self.f.cid)
            if target_scene.get("type") == "quiz":
                target_scene["content"]["questions"][0]["questionAudioUrl"] = target_action["audioUrl"]
            saved = deepcopy(target)
            original_receipts = deepcopy(receipts)
            new_receipts = [deepcopy(receipt)]
            receipts += new_receipts
            documents = {"source.json": source, "target-text.json": target_text,
                "target.json": target, "saved.json": saved, "original-plan.json": self.f.plan,
                "original-receipts.json": original_receipts, "new-receipts.json": new_receipts,
                "receipts.json": receipts, "plan.json": child}
            for name, value in documents.items():
                self.write(archive / name, value)
            intent_files = {name: hashlib.sha256((archive / name).read_bytes()).hexdigest() for name in (
                "source.json", "target-text.json", "original-plan.json", "original-receipts.json", "plan.json")}
            intent = {"schemaVersion": "mira.textbook.preview-narration-intent.v1",
                "revisionId": revision_id, "files": intent_files}
            intent["sha256"] = digest(intent)
            self.write(archive / "intent.json", intent)
            amendment = {"schemaVersion": "mira.textbook.preview-narration-amendment.v2",
                "revisionId": revision_id, "intentSha256": intent["sha256"],
                "sourceSha256": digest(source), "targetSha256": digest(saved),
                "audioPlanSha256": digest(child), "newTtsRequestIds": [receipt["requestId"]]}
            amendment["sha256"] = digest(amendment)
            self.write(archive / "amendment.json", amendment)
            classroom, plans[revision_id] = saved, child

        by_id = {item["requestId"]: item for item in receipts}
        targets, origins = [], []
        for scene in classroom["scenes"]:
            for action in scene.get("actions", []):
                if action.get("type") != "speech":
                    continue
                receipt = by_id[action["audioId"]]
                audio = (self.audio_directory / "audio" / (action["audioId"] + ".wav")).read_bytes()
                self.fixture.audio = audio
                entry = self.fixture.audit_entry(scene, action, receipt, action["text"])
                request_plan = plans.get(receipt.get("narrationRevisionId"))
                target = {"sceneId": scene["id"], "sceneOrder": scene.get("order", 0),
                    "action": deepcopy(action), "ttsReceipt": deepcopy(receipt),
                    "requestPlan": deepcopy(request_plan), "audioBase64": base64.b64encode(audio).decode()}
                response = entry["asr"]
                attempt = {"kind": "formal", "role": "routine", "source": deepcopy(target),
                    "plan": deepcopy(self.f.plan), "classroomId": self.f.cid,
                    "request": formal_request(target, self.f.plan, self.f.cid, response["requestId"]),
                    "response": deepcopy(response)}
                origin = {"schemaVersion": ORIGIN_SCHEMA, "kind": "formal", "source": deepcopy(target),
                    "plan": deepcopy(self.f.plan), "classroomId": self.f.cid, "attempts": [attempt]}
                targets.append({"target": target, "originSha256": digest(origin)})
                origins.append(origin)
        self.fixture.audio = base_audio
        self.f.classroom = classroom
        self.fixture.receipts = receipts
        self.audit = build_audit(plan=self.f.plan, classroom=classroom, targets=targets, origins=origins)
        self.source_sha = digest(classroom)
        self.core_sha = digest(teaching_core(classroom))
        self.write(self.classroom_path, classroom)
        self.write(self.audio_directory / "textbook-preview-audio" / "receipts.json", receipts)
        self.write(self.audit_path, self.audit)
        return ["a" * 64, "b" * 64]

    def runtime(self):
        runtime = Mock(base_url="http://127.0.0.1:3100")
        runtime.rooms = {self.f.cid: deepcopy(self.f.classroom)}
        def get(room_id):
            if room_id not in runtime.rooms:
                raise OpenMaicFullRuntimeError("missing", "missing", status_code=404)
            return deepcopy(runtime.rooms[room_id])
        def save(value):
            runtime.rooms[value["id"]] = {**deepcopy(value), "createdAt": "normalized-api-time"}
        runtime.get_classroom.side_effect = get
        runtime.save_preview_classroom.side_effect = save
        return runtime

    def test_prepare_validates_complete_v3_origin_chain_and_builds_narration_only_alias(self):
        with patch("scripts.private_textbook_preview_snapshot.OpenMaicFullRuntimeClient") as client:
            manifest = self.prepare()
        client.assert_not_called()
        _, checked, alias = load_snapshot(self.output)
        self.assertEqual(checked, manifest)
        self.assertEqual(manifest["schemaVersion"], PINYIN_ORIGIN_SCHEMA)
        self.assertEqual(manifest["verification"]["speechCount"], 3)
        self.assertEqual(manifest["verification"]["receiptCount"], 3)
        self.assertEqual(manifest["verification"]["wavCount"], 3)
        self.assertEqual(manifest["verification"]["originAuditSegmentCount"], 3)
        self.assertEqual(len(manifest["audioAssets"]), 3)
        self.assertIs(alias["stage"]["miraTextbookPreviewNarration"], True)
        self.assertNotIn("fixedTextbook", alias["stage"])
        self.assertTrue(all(path.read_bytes() == value for path, value in self.original_bytes.items()))

    def test_prepare_accepts_sequential_revision_chain_and_selects_only_active_receipts(self):
        revisions = self.sequential_revisions()
        manifest = self.prepare()
        self.assertEqual(manifest["verification"]["revisionCount"], 2)
        self.assertEqual(manifest["verification"]["activeRevisionCount"], 2)
        self.assertEqual(manifest["verification"]["speechCount"], 3)
        self.assertEqual(manifest["verification"]["receiptCount"], 3)
        self.assertEqual(manifest["verification"]["storedReceiptCount"], 5)
        self.assertEqual(manifest["verification"]["wavCount"], 3)
        self.assertEqual(manifest["verification"]["storedWavCount"], 5)
        self.assertEqual({item["target"]["ttsReceipt"]["narrationRevisionId"] for item in self.audit["segments"]
                          if item["target"]["requestPlan"] is not None}, set(revisions))

    def test_missing_terminal_revision_archive_is_rejected(self):
        revisions = self.sequential_revisions()
        shutil.rmtree(self.audio_directory / "textbook-preview-audio" / "narration-revisions" / revisions[-1])
        with self.assertRaisesRegex(ValueError, "final_revision_missing"):
            self.prepare()

    def test_wrong_revision_parent_is_rejected_even_when_archive_hashes_are_resealed(self):
        revisions = self.sequential_revisions()
        archive = self.audio_directory / "textbook-preview-audio" / "narration-revisions" / revisions[-1]
        plan_path = archive / "plan.json"
        child = json.loads(plan_path.read_text())
        child["parentPlanSha256"] = "0" * 64
        self.write(plan_path, child)
        intent_path = archive / "intent.json"
        intent = json.loads(intent_path.read_text())
        intent["files"]["plan.json"] = hashlib.sha256(plan_path.read_bytes()).hexdigest()
        intent["sha256"] = digest({k: v for k, v in intent.items() if k != "sha256"})
        self.write(intent_path, intent)
        amendment_path = archive / "amendment.json"
        amendment = json.loads(amendment_path.read_text())
        amendment["intentSha256"] = intent["sha256"]
        amendment["audioPlanSha256"] = digest(child)
        amendment["sha256"] = digest({k: v for k, v in amendment.items() if k != "sha256"})
        self.write(amendment_path, amendment)
        with self.assertRaisesRegex(ValueError, "revision_parent_mismatch"):
            self.prepare()

    def test_changed_target_or_amendment_hash_and_duplicate_receipt_are_rejected(self):
        revisions = self.sequential_revisions()
        archive = self.audio_directory / "textbook-preview-audio" / "narration-revisions" / revisions[-1]
        target_path = archive / "target-text.json"
        original_target = target_path.read_bytes()
        target = json.loads(original_target)
        target["scenes"][0]["actions"][0]["text"] += "篡改"
        self.write(target_path, target)
        intent_path = archive / "intent.json"
        original_intent = intent_path.read_bytes()
        intent = json.loads(original_intent)
        intent["files"]["target-text.json"] = hashlib.sha256(target_path.read_bytes()).hexdigest()
        intent["sha256"] = digest({k: v for k, v in intent.items() if k != "sha256"})
        self.write(intent_path, intent)
        amendment_path = archive / "amendment.json"
        original_amendment = amendment_path.read_bytes()
        amendment = json.loads(original_amendment)
        amendment["intentSha256"] = intent["sha256"]
        amendment["sha256"] = digest({k: v for k, v in amendment.items() if k != "sha256"})
        self.write(amendment_path, amendment)
        with self.assertRaisesRegex(ValueError, "revision_target_mismatch"):
            self.prepare()
        target_path.write_bytes(original_target)
        intent_path.write_bytes(original_intent)
        amendment_path.write_bytes(original_amendment)

        amendment = json.loads(original_amendment)
        amendment["sha256"] = "0" * 64
        self.write(amendment_path, amendment)
        with self.assertRaisesRegex(ValueError, "revision_hash_mismatch"):
            self.prepare()
        amendment_path.write_bytes(original_amendment)

        receipts_path = self.audio_directory / "textbook-preview-audio" / "receipts.json"
        receipts = json.loads(receipts_path.read_text())
        self.write(receipts_path, receipts + [deepcopy(receipts[0])])
        with self.assertRaisesRegex(ValueError, "receipts_invalid"):
            self.prepare()

    def test_pinyin_snapshot_uses_the_existing_guarded_save_and_readback_path(self):
        manifest = self.prepare()
        runtime = self.runtime()
        result = save_snapshot(self.output, runtime,
            expected_runtime_core_sha256=manifest["expectedRuntimeCoreSha256"])
        self.assertEqual(result["status"], "saved_private_preview")
        saved = runtime.save_preview_classroom.call_args.args[0]
        self.assertIs(saved["stage"]["miraTextbookPreviewNarration"], True)
        self.assertNotIn("fixedTextbook", saved["stage"])
        self.assertEqual(result["readbackPersistedSha256"], manifest["aliasPersistedSha256"])

    def test_wrong_source_core_plan_or_count_never_creates_a_snapshot(self):
        cases = ({"expected_source_sha256": "0" * 64}, {"expected_core_sha256": "0" * 64},
                 {"expected_plan_sha256": "0" * 64}, {"expected_speech_count": 4})
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.prepare(**change)
            self.assertFalse(self.output.exists())

    def test_missing_receipt_changed_wav_or_changed_origin_audit_is_rejected(self):
        receipts_path = self.audio_directory / "textbook-preview-audio" / "receipts.json"
        receipts = deepcopy(self.fixture.receipts)
        self.write(receipts_path, receipts[:-1])
        with self.assertRaises((ValueError, ApiError)):
            self.prepare()
        self.write(receipts_path, receipts)
        wav = self.audio_directory / "audio" / (receipts[0]["requestId"] + ".wav")
        original = wav.read_bytes()
        wav.write_bytes(original[:-2] + b"\x05\x00")
        with self.assertRaises((ValueError, ApiError)):
            self.prepare()
        wav.write_bytes(original)
        changed = deepcopy(self.audit)
        changed["segments"][0]["target"]["ttsReceipt"]["providerRequestId"] = "changed"
        changed["sha256"] = digest({k: v for k, v in changed.items() if k != "sha256"})
        self.write(self.audit_path, changed)
        with self.assertRaises((ValueError, ApiError)):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_interactive_helper_and_quiz_audio_must_match_exact_formal_speech(self):
        room = "room-pinyin"
        urls = {"find-cat": f"/api/classroom-media/{room}/audio/a.wav",
                "try-again": f"/api/classroom-media/{room}/audio/b.wav"}
        classroom = {"id": room, "stage": {"id": room}, "scenes": [
            {"id": "interactive", "type": "interactive", "actions": [
                {"id": "a", "type": "speech", "text": "请看小猫。", "audioId": "a", "audioUrl": urls["find-cat"]},
                {"id": "b", "type": "speech", "text": "再看一看。", "audioId": "b", "audioUrl": urls["try-again"]}],
             "content": {"html": bind_interactive_audio(activity(), urls, room)}},
            {"id": "quiz", "type": "quiz", "actions": [
                {"id": "q", "type": "speech", "text": "请选择小猫。", "audioId": "q",
                 "audioUrl": f"/api/classroom-media/{room}/audio/q.wav"}],
             "content": {"questions": [{"id": "question", "question": "请选择小猫。",
                 "questionAudioUrl": f"/api/classroom-media/{room}/audio/q.wav"}]}}]}
        verify_pinyin_playback_bindings(classroom, {"a", "b", "q"}, "http://127.0.0.1:3100")
        from content.textbook_interactive_narration import (
            _helper, _WAITING_AUDIO_CODE, _QUEUE_AUDIO_CODE, _INTERRUPTING_AUDIO_CODE)
        for code in (_WAITING_AUDIO_CODE, _QUEUE_AUDIO_CODE, _INTERRUPTING_AUDIO_CODE):
            legacy = deepcopy(classroom)
            legacy["scenes"][0]["content"]["html"] = activity().replace(
                "<head>", "<head>" + _helper(urls, code), 1)
            verify_pinyin_playback_bindings(legacy, {"a", "b", "q"}, "http://127.0.0.1:3100")
        bad = deepcopy(classroom)
        bad["scenes"][0]["content"]["html"] = bad["scenes"][0]["content"]["html"].replace(
            "/audio/a.wav", "/audio/b.wav", 1)
        with self.assertRaises(ValueError):
            verify_pinyin_playback_bindings(bad, {"a", "b", "q"}, "http://127.0.0.1:3100")
        bad = deepcopy(classroom)
        bad["scenes"][1]["content"]["questions"][0]["questionAudioUrl"] = urls["find-cat"]
        with self.assertRaises(ValueError):
            verify_pinyin_playback_bindings(bad, {"a", "b", "q"}, "http://127.0.0.1:3100")


if __name__ == "__main__":
    unittest.main()
