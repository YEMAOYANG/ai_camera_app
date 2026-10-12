"""New private identities retain exact original audio without paid replay."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from content.textbook_catalog import digest
from content.textbook_audio_language import ENGLISH_AUTO_LANGUAGE_POLICY, ENGLISH_AUTO_LANGUAGE_POLICY_SHA256
from services.textbook_batch_audio import (
    AUDIO_CLONE_INHERITANCE_SCHEMA, AUDIO_INSERTION_CLONE_SCHEMA, AUDIO_SCENE_INSERTION_CLONE_SCHEMA,
    build_audio_plan, _segment_requests,
)
from content.teacher_profiles import get_formal_subject_qwen_voice_identity
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from tests import test_textbook_batch_audio as audio_fixtures


class AudioCloneInheritanceTest(unittest.TestCase):
    def setUp(self):
        self.case = audio_fixtures.TextbookBatchAudioTest(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        case = self.case
        runtime, value, _ = case.inheritance(preceding=2)
        self.runtime = runtime
        source = (case.root / "source").resolve()
        target = (case.root / "target").resolve()
        source.mkdir()
        target.mkdir()
        old_audit = Path(value["sourceAudioAuditDirectory"])
        old_audit.rename(source / "audio-audit")
        source_plan = json.loads((source / "audio-audit/plan.json").read_text())
        old_room = deepcopy(case.room)
        for action, item in zip(old_room["scenes"][0]["actions"], source_plan["workload"]):
            action["text"] = item["text"]
        assert digest(old_room) == source_plan["sourceSha256"]
        case.room["id"] = case.room["stage"]["id"] = "synthetic-new-room"
        case.local_file = case.store / "synthetic-new-room.json"
        case.local_file.write_text(json.dumps(case.room))
        runtime.saved = deepcopy(case.room)
        case.output = target / "audio-audit"
        task = "a" * 64
        for directory, room in ((source, old_room), (target, case.room)):
            frozen = {"taskId": task, "binding": case.binding}
            frozen["inputSha256"] = digest(frozen)
            (directory / "input.json").write_text(json.dumps(frozen))
            (directory / "classroom.json").write_text(json.dumps(room))
        plan = build_audio_plan(case.room, case.binding, runtime.base_url)
        value.update(schemaVersion=AUDIO_CLONE_INHERITANCE_SCHEMA, taskId=task,
            sourceCandidateDirectory=str(source), targetCandidateDirectory=str(target),
            sourceAudioAuditDirectory=str(source / "audio-audit"),
            targetPlanSha256=digest(plan), targetSourceSha256=plan["sourceSha256"])
        self.value = value
        self.originals = {p: p.read_bytes() for p in source.rglob("*") if p.is_file()}
        runtime.start_formal_audio_tts.reset_mock()
        runtime.start_formal_audio_asr.reset_mock()
        runtime.download_formal_audio_tts.reset_mock()
        runtime.save_preview_classroom.reset_mock()

    def run_audio(self, value=None):
        return self.case.narrate(self.runtime, audio_inheritance=value or self.value)

    def assert_no_paid_calls(self):
        self.runtime.start_formal_audio_tts.assert_not_called()
        self.runtime.start_formal_audio_asr.assert_not_called()
        self.runtime.download_formal_audio_tts.assert_not_called()
        self.runtime.save_preview_classroom.assert_not_called()

    def test_exact_clone_copies_old_wav_and_pays_only_for_changed_sentence(self):
        result = self.run_audio()
        self.assertTrue(result["allSegmentsPassed"])
        self.runtime.start_formal_audio_tts.assert_called_once()
        self.runtime.start_formal_audio_asr.assert_called_once()
        self.runtime.download_formal_audio_tts.assert_called_once()
        for segment, old in zip(result["segments"][:2], self.value["segments"]):
            self.assertEqual(segment["ttsRequestId"], old["ttsRequestId"])
            self.assertEqual(segment["asrRequestId"], old["asrRequestId"])
            self.assertEqual(segment["inheritedFrom"]["schemaVersion"], AUDIO_CLONE_INHERITANCE_SCHEMA)
            path = self.case.store / self.case.room["id"] / "audio" / (segment["ttsRequestId"] + ".wav")
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), old["audioSha256"])
            self.assertFalse((self.case.output / (segment["ttsRequestId"] + ".json")).exists())
        for path, raw in self.originals.items():
            self.assertEqual(path.read_bytes(), raw)
        self.run_audio()
        self.runtime.start_formal_audio_tts.assert_called_once()
        self.runtime.start_formal_audio_asr.assert_called_once()

    def test_different_task_and_forged_input_hash_stop_before_provider(self):
        source = Path(self.value["sourceCandidateDirectory"]) / "input.json"
        original = source.read_bytes()
        for recompute in (False, True):
            frozen = json.loads(original)
            frozen["taskId"] = "b" * 64
            if recompute:
                frozen["inputSha256"] = digest({k: v for k, v in frozen.items() if k != "inputSha256"})
            source.write_text(json.dumps(frozen))
            with self.assertRaisesRegex(ValueError, "audio_clone_frozen_lineage_mismatch"):
                self.run_audio()
            self.assert_no_paid_calls()
        source.write_bytes(original)

    def refreeze_target(self):
        room = self.case.room
        self.case.local_file.write_text(json.dumps(room))
        self.runtime.saved = deepcopy(room)
        (Path(self.value['targetCandidateDirectory']) / 'classroom.json').write_text(json.dumps(room))
        plan = build_audio_plan(room, self.case.binding, self.runtime.base_url)
        self.value.update(targetPlanSha256=digest(plan), targetSourceSha256=plan['sourceSha256'])

    def test_inserted_cue_preserves_original_audio_without_rebuying_later_cues(self):
        self.value['schemaVersion'] = AUDIO_INSERTION_CLONE_SCHEMA
        self.case.room['scenes'][0]['actions'].insert(1, {
            'id': 'inserted-cue', 'type': 'speech', 'text': '请看小猫。'})
        self.refreeze_target()
        by_id = {a['id']: a['text'] for a in self.case.room['scenes'][0]['actions']}
        def recognize(**payload):
            transcript = by_id[payload['action_id']]
            return {'requestId': payload['request_id'], 'status': 'succeeded',
                    'transcript': transcript, 'completionUsable': True,
                    'transcriptSha256': hashlib.sha256(transcript.encode()).hexdigest()}
        self.runtime.start_formal_audio_asr.side_effect = recognize
        result = self.run_audio()
        inherited = [s for s in result['segments'] if 'inheritedFrom' in s]
        self.assertEqual([s['ttsRequestId'] for s in inherited],
                         [s['ttsRequestId'] for s in self.value['segments']])
        self.assertEqual(self.runtime.start_formal_audio_tts.call_count, 2)
        self.assertEqual(self.runtime.start_formal_audio_asr.call_count, 2)
        self.run_audio()
        self.assertEqual(self.runtime.start_formal_audio_tts.call_count, 2)
        for path, raw in self.originals.items():
            self.assertEqual(path.read_bytes(), raw)

    def test_inserted_cue_policy_still_rejects_reordering_or_changed_speech(self):
        original = deepcopy(self.case.room)
        self.value['schemaVersion'] = AUDIO_INSERTION_CLONE_SCHEMA
        for mutation in ('order', 'text'):
            self.case.output = Path(self.value['targetCandidateDirectory']) / ('audio-audit-' + mutation)
            self.case.room = deepcopy(original)
            actions = self.case.room['scenes'][0]['actions']
            if mutation == 'order':
                actions[:2] = reversed(actions[:2])
            else:
                actions[1]['text'] = '不能继承另一句话。'
            self.refreeze_target()
            with self.assertRaisesRegex(ValueError, 'audio_inheritance_teaching_segment_changed'):
                self.run_audio()
            self.assert_no_paid_calls()

    def insert_teaching_scene(self):
        scene = deepcopy(self.case.room['scenes'][0])
        scene.update(id='inserted-scene', actions=[{
            'id': 'inserted-scene-cue', 'type': 'speech', 'text': '先听示范，再做练习。'}])
        self.case.room['scenes'].insert(0, scene)
        self.refreeze_target()
        texts = {a['id']: a['text'] for s in self.case.room['scenes'] for a in s['actions']}
        def recognize(**payload):
            transcript = texts[payload['action_id']]
            return {'requestId': payload['request_id'], 'status': 'succeeded',
                    'transcript': transcript, 'completionUsable': True,
                    'transcriptSha256': hashlib.sha256(transcript.encode()).hexdigest()}
        self.runtime.start_formal_audio_asr.side_effect = recognize

    def test_explicit_scene_insertion_keeps_original_paid_request_and_wav(self):
        self.value['schemaVersion'] = AUDIO_SCENE_INSERTION_CLONE_SCHEMA
        self.insert_teaching_scene()
        result = self.run_audio()
        inherited = [s for s in result['segments'] if 'inheritedFrom' in s]
        self.assertEqual([s['ttsRequestId'] for s in inherited],
                         [s['ttsRequestId'] for s in self.value['segments']])
        self.assertEqual(self.runtime.start_formal_audio_tts.call_count, 2)
        self.assertEqual(self.runtime.start_formal_audio_asr.call_count, 2)
        for segment in inherited:
            wav = self.case.store / self.case.room['id'] / 'audio' / (segment['ttsRequestId'] + '.wav')
            self.assertEqual(hashlib.sha256(wav.read_bytes()).hexdigest(), segment['audioSha256'])
        self.run_audio()
        self.assertEqual(self.runtime.start_formal_audio_tts.call_count, 2)
        for path, raw in self.originals.items():
            self.assertEqual(path.read_bytes(), raw)

    def test_existing_cue_insertion_policy_does_not_silently_allow_scene_insertion(self):
        self.value['schemaVersion'] = AUDIO_INSERTION_CLONE_SCHEMA
        self.insert_teaching_scene()
        with self.assertRaisesRegex(ValueError, 'audio_inheritance_teaching_segment_changed'):
            self.run_audio()
        self.assert_no_paid_calls()

    def test_scene_insertion_rejects_missing_scene_moved_cue_and_changed_speech(self):
        self.value['schemaVersion'] = AUDIO_SCENE_INSERTION_CLONE_SCHEMA
        self.insert_teaching_scene()
        original = deepcopy(self.case.room)
        for mutation in ('missing_scene', 'moved_cue', 'changed_speech', 'reordered_cue'):
            self.case.room = deepcopy(original)
            self.case.output = Path(self.value['targetCandidateDirectory']) / ('audio-audit-' + mutation)
            scene = self.case.room['scenes'][1]
            if mutation == 'missing_scene':
                scene['id'] = 'renamed-original-scene'
            elif mutation == 'moved_cue':
                self.case.room['scenes'][0]['actions'].append(scene['actions'].pop(0))
            elif mutation == 'changed_speech':
                scene['actions'][0]['text'] = '这句话改变了，不能继承。'
            else:
                scene['actions'][:2] = reversed(scene['actions'][:2])
            self.refreeze_target()
            with self.assertRaisesRegex(ValueError, 'audio_inheritance_(source_scene|teaching_segment)'):
                self.run_audio()
            self.assert_no_paid_calls()

    def test_target_classroom_drift_stops_before_provider(self):
        target = Path(self.value["targetCandidateDirectory"]) / "classroom.json"
        room = json.loads(target.read_text())
        room["scenes"][0]["actions"][0]["text"] = "请看小狗。"
        target.write_text(json.dumps(room))
        with self.assertRaisesRegex(ValueError, "audio_clone_frozen_lineage_mismatch"):
            self.run_audio()
        self.assert_no_paid_calls()

    def test_original_wav_change_stops_before_any_copy_or_provider(self):
        old = self.value["segments"][0]
        path = self.case.store / "synthetic-room/audio" / (old["ttsRequestId"] + ".wav")
        path.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "audio_inheritance_audio_mismatch"):
            self.run_audio()
        self.assert_no_paid_calls()
        self.assertFalse(any((self.case.store / self.case.room["id"] / "audio").glob("*.wav")))

    def test_ambiguous_source_receipt_cannot_be_inherited(self):
        old = self.value["segments"][0]
        path = Path(self.value["sourceAudioAuditDirectory"]) / (old["ttsRequestId"] + ".json")
        value = json.loads(path.read_text())
        value["state"] = "dispatching"
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "asr_reconciliation_requires_known_success"):
            self.run_audio()
        self.assert_no_paid_calls()

    def test_existing_target_dispatch_is_not_hidden_by_inheritance(self):
        case = self.case
        plan = build_audio_plan(case.room, case.binding, self.runtime.base_url)
        request, _, _, _ = _segment_requests(plan, plan["workload"][0],
            get_formal_subject_qwen_voice_identity(case.binding["subject"]))
        case.output.mkdir()
        (case.output / (request + ".json")).write_text('{"state":"dispatching"}')
        with self.assertRaisesRegex(ValueError, "audio_inheritance_conflicts_with_target_dispatch"):
            self.run_audio()
        self.assert_no_paid_calls()


class AutoAudioCloneInheritanceTest(unittest.TestCase):
    def setUp(self):
        self.case = audio_fixtures.TextbookBatchAudioTest(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        case = self.case
        case.binding["subject"] = "english"
        case.room["scenes"][0]["actions"].append({
            "id": "speech-2", "type": "speech", "text": "请看小猫。"})
        case.local_file.write_text(json.dumps(case.room))
        source, target = case.root / "source", case.root / "target"
        source.mkdir()
        target.mkdir()
        case.output = source / "audio-audit-english-auto-v1"
        runtime = case.runtime()
        self.runtime = runtime
        profile = {"policyVersion": ENGLISH_AUTO_LANGUAGE_POLICY["policyVersion"],
            "policySha256": ENGLISH_AUTO_LANGUAGE_POLICY_SHA256, "providerBodySha256": "c" * 64}
        old_tts = runtime.start_formal_audio_tts.side_effect
        runtime.start_formal_audio_tts.side_effect = lambda **payload: {
            **old_tts(**payload), "providerLanguagePolicy": deepcopy(profile)}
        self.transcripts = {"speech-1": "请看小猫。", "speech-2": "请看小猫。"}

        def recognize(**payload):
            text = self.transcripts[payload["action_id"]]
            return {"requestId": payload["request_id"], "status": "succeeded", "transcript": text,
                "transcriptSha256": hashlib.sha256(text.encode()).hexdigest(), "completionUsable": True,
                "providerLanguagePolicy": deepcopy(profile)}
        runtime.start_formal_audio_asr.side_effect = recognize
        case.narrate(runtime, audio_language_policy="english-auto-v1")
        self.source_audit = case.output
        old_room = deepcopy(case.room)
        case.room["id"] = case.room["stage"]["id"] = "synthetic-new-auto-room"
        case.room["scenes"][0]["actions"][1]["text"] = "请看小狗。"
        self.transcripts["speech-2"] = "请看小狗。"
        case.local_file = case.store / (case.room["id"] + ".json")
        case.local_file.write_text(json.dumps(case.room))
        runtime.saved = deepcopy(case.room)
        case.output = target / "audio-audit-english-auto-v1"
        task = "a" * 64
        for directory, room in ((source, old_room), (target, case.room)):
            frozen = {"taskId": task, "binding": case.binding}
            frozen["inputSha256"] = digest(frozen)
            (directory / "input.json").write_text(json.dumps(frozen))
            (directory / "classroom.json").write_text(json.dumps(room))
        source_plan = json.loads((self.source_audit / "plan.json").read_text())
        source_audit = json.loads((self.source_audit / "audit.json").read_text())
        plan = build_audio_plan(case.room, case.binding, runtime.base_url, audio_language_policy="english-auto-v1")
        entry = {key: source_audit["segments"][0][key] for key in (
            "sceneId", "segmentId", "textSha256", "ttsRequestId", "asrRequestId", "audioSha256", "similarityBps")}
        for kind in ("tts", "asr"):
            receipt = json.loads((self.source_audit / (entry[kind + "RequestId"] + ".json")).read_text())["receipt"]
            entry[kind + "ReceiptSha256"] = digest(receipt)
        self.value = {"schemaVersion": AUDIO_CLONE_INHERITANCE_SCHEMA, "taskId": task,
            "sourceCandidateDirectory": str(source.resolve()), "targetCandidateDirectory": str(target.resolve()),
            "sourceAudioAuditDirectory": str(self.source_audit.resolve()),
            "sourcePlanSha256": digest(source_plan), "sourceAuditSha256": digest(source_audit),
            "sourceSha256": source_plan["sourceSha256"], "targetPlanSha256": digest(plan),
            "targetSourceSha256": plan["sourceSha256"], "segments": [entry]}
        self.originals = {p: p.read_bytes() for p in source.rglob("*") if p.is_file()}
        self.original_wavs = {p: p.read_bytes() for p in (case.store / old_room["id"] / "audio").glob("*.wav")}
        for method in (runtime.start_formal_audio_tts, runtime.start_formal_audio_asr,
                       runtime.download_formal_audio_tts, runtime.save_preview_classroom):
            method.reset_mock()

    def run_audio(self):
        return self.case.narrate(self.runtime, audio_inheritance=self.value, audio_language_policy="english-auto-v1")

    def test_exact_auto_policy_reuses_original_receipts_without_new_paid_calls_for_inherited_cue(self):
        result = self.run_audio()
        self.assertTrue(result["allSegmentsPassed"])
        self.assertEqual(result["segments"][0]["ttsRequestId"], self.value["segments"][0]["ttsRequestId"])
        self.assertEqual(result["segments"][0]["asrRequestId"], self.value["segments"][0]["asrRequestId"])
        self.runtime.start_formal_audio_tts.assert_called_once()
        self.runtime.start_formal_audio_asr.assert_called_once()
        self.assertEqual(self.runtime.start_formal_audio_tts.call_args.kwargs["action_id"], "speech-2")
        for path, raw in {**self.originals, **self.original_wavs}.items():
            self.assertEqual(path.read_bytes(), raw)

    def test_missing_or_drifted_physical_auto_policy_blocks_before_any_copy_or_provider(self):
        entry = self.value["segments"][0]
        for kind in ("tts", "asr"):
            path = self.source_audit / (entry[kind + "RequestId"] + ".json")
            original = path.read_bytes()
            expected_hash = entry[kind + "ReceiptSha256"]
            for mutation in (None, {"policyVersion": "other"}, {"policySha256": "f" * 64},
                             {"providerBodySha256": "invalid"}, {"unexpected": True}):
                with self.subTest(kind=kind, mutation=mutation):
                    checkpoint = json.loads(original)
                    if mutation is None:
                        checkpoint["receipt"].pop("providerLanguagePolicy")
                    else:
                        checkpoint["receipt"]["providerLanguagePolicy"].update(mutation)
                    path.write_text(json.dumps(checkpoint))
                    # Re-freeze the synthetic manifest hash so this tests the
                    # physical policy, rather than the existing hash guard.
                    entry[kind + "ReceiptSha256"] = digest(checkpoint["receipt"])
                    with self.assertRaisesRegex(OpenMaicFullRuntimeError, "英语批量语音策略回执不一致"):
                        self.run_audio()
                    for method in (self.runtime.start_formal_audio_tts, self.runtime.start_formal_audio_asr,
                                   self.runtime.download_formal_audio_tts, self.runtime.save_preview_classroom):
                        method.assert_not_called()
                    self.assertFalse(any((self.case.store / self.case.room["id"] / "audio").glob("*.wav")))
                    for wav, raw in self.original_wavs.items():
                        self.assertEqual(wav.read_bytes(), raw)
            path.write_bytes(original)
            entry[kind + "ReceiptSha256"] = expected_hash


if __name__ == "__main__":
    unittest.main()
