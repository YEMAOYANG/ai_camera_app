"""Paid narration checkpoints must fence uncertainty and exact teaching identity."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import stat
import unittest
from unittest.mock import Mock, patch
import wave

from content.teacher_profiles import get_formal_subject_qwen_voice_identity, get_formal_runtime_teacher_contract, get_teacher_profile
from content.textbook_batch_generation import INPUT_SCHEMA
from content.textbook_catalog import digest
from content.textbook_pedagogy import teaching_profile
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from scripts.narrate_textbook_batch import load_candidate, main
from services.textbook_batch_audio import (ASR_RECONCILIATION_REASON, ASR_RECONCILIATION_SCHEMA,
    AUDIO_INHERITANCE_SCHEMA, _external_once, _segment_requests, build_audio_plan,
    load_asr_reconciliation_file, load_audio_inheritance_file, narrate_candidate, narration_workload,
    normalize_audio_inheritance)
from tests.test_textbook_batch import manifest
from tests.test_textbook_interactive_narration import activity
from content.textbook_number_spelling import page_number_equivalence, validate_page_number_equivalence


def missing():
    return OpenMaicFullRuntimeError("not_found", "not_found", status_code=404)


def classroom():
    return {"id": "synthetic-room", "stage": {"id": "synthetic-room"}, "scenes": [
        {"id": "scene-1", "order": 1, "type": "slide", "actions": [
            {"id": "speech-1", "type": "speech", "text": "请看小猫。"}]}]}


def wav_bytes():
    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 1600)
    return stream.getvalue()


class TextbookBatchAudioTest(unittest.TestCase):
    def test_page_number_equivalence_is_exact_and_rejects_wrong_numbers_or_words(self):
        def receipt(text):
            return {'requestId':'asr-test','status':'succeeded','transcript':text,
                    'transcriptSha256':hashlib.sha256(text.encode()).hexdigest(),'completionUsable':True}
        expected='音节旁边标着演示页码12。接着翻到这个练习的第12页。'
        proof=page_number_equivalence(expected,receipt('音节旁边标着演示页码十二，接着翻到这个练习的第十二页。'))
        self.assertIsNotNone(proof);self.assertEqual(proof['pageNumberOccurrences'],2)
        validate_page_number_equivalence(expected,proof)
        for actual in ['音节旁边标着演示页码二十，接着翻到这个练习的第十二页。',
                       '音节旁边标着演示页码十二，接着翻到那个练习的第十二页。']:
            self.assertIsNone(page_number_equivalence(expected,receipt(actual)))
        for text,actual in [('页码12.5','页码十二点五'),('页码012','页码十二'),
                            ('页码1200','页码一千二百'),('电话12','电话十二'),
                            ('页码12万','页码十二万'),('第12年','第十二年')]:
            self.assertIsNone(page_number_equivalence(text,receipt(actual)))
        for text,actual in [('第101页','第一百零一页'),('第110页','第一百一十页'),('页码999','页码九百九十九')]:
            self.assertIsNotNone(page_number_equivalence(text,receipt(actual)))
        changed=deepcopy(proof);changed['asrReceipt']['transcript']='第十一页'
        with self.assertRaisesRegex(ValueError,'evidence_changed'):validate_page_number_equivalence(expected,changed)

    def test_page_number_review_reuses_successful_paid_receipts_in_separate_audit(self):
        text='音节旁边标着演示页码12。接着翻到这个练习的第12页。'
        transcript='音节旁边标着演示页码十二，接着翻到这个练习的第十二页。'
        self.room['scenes'][0]['actions'][0]['text']=text
        self.local_file.write_text(json.dumps(self.room));runtime=self.runtime()
        runtime.start_formal_audio_asr.side_effect=lambda **p:{'requestId':p['request_id'],
            'status':'succeeded','transcript':transcript,'transcriptSha256':hashlib.sha256(transcript.encode()).hexdigest(),
            'completionUsable':True}
        with self.assertRaisesRegex(RuntimeError,'semantic_review_required'):self.narrate(runtime)
        original=(self.output/'audit.json').read_bytes();reviewed=self.root/'audio-audit-page-numbers-v1';reviewed.mkdir()
        for p in [self.output/'plan.json',*self.output.glob('tbb*.json')]:
            (reviewed/p.name).write_bytes(p.read_bytes())
        runtime.reset_mock()
        result=narrate_candidate(runtime,self.room,self.binding,reviewed,self.store,allow_page_number_equivalence=True)
        runtime.start_formal_audio_tts.assert_not_called();runtime.start_formal_audio_asr.assert_not_called()
        runtime.download_formal_audio_tts.assert_not_called()
        self.assertEqual((self.output/'audit.json').read_bytes(),original)
        self.assertLess(result['segments'][0]['literalScoreBps'],8500)
        self.assertEqual(result['segments'][0]['similarityBps'],10000)
        from scripts.private_textbook_preview_snapshot import verify_complete_audio
        plan=json.loads((reviewed/'plan.json').read_text());narrated=json.loads((reviewed/'narrated-classroom.json').read_text())
        verify_complete_audio(self.room,narrated,plan,result,self.store)
        result['segments'][0]['pageNumberEquivalence']['normalizedTextSha256']='0'*64
        result['sha256']=digest({k:v for k,v in result.items() if k!='sha256'})
        with self.assertRaisesRegex(ValueError,'evidence_changed'):verify_complete_audio(self.room,narrated,plan,result,self.store)

    def test_page_number_inheritance_binds_actual_receipt_and_never_repays(self):
        text = '请翻到第12页。'
        transcript = '请翻到第十二页。'
        self.room['scenes'][0]['actions'][0]['text'] = text
        self.local_file.write_text(json.dumps(self.room))
        runtime = self.runtime()
        runtime.start_formal_audio_asr.side_effect = lambda **p: {
            'requestId': p['request_id'], 'status': 'succeeded', 'transcript': transcript,
            'transcriptSha256': hashlib.sha256(transcript.encode()).hexdigest(), 'completionUsable': True}
        source = (self.root / 'source' / 'audio-audit-page-numbers-v1').resolve()
        old_audit = narrate_candidate(runtime, self.room, self.binding, source, self.store,
                                      allow_page_number_equivalence=True)
        old_plan = json.loads((source / 'plan.json').read_text())
        segment = old_audit['segments'][0]
        self.assertLess(segment['literalScoreBps'], 8500)
        entry = {k: segment[k] for k in ('sceneId', 'segmentId', 'textSha256',
            'ttsRequestId', 'asrRequestId', 'audioSha256', 'similarityBps')}
        for kind in ('tts', 'asr'):
            receipt = json.loads((source / (entry[kind+'RequestId']+'.json')).read_text())['receipt']
            entry[kind+'ReceiptSha256'] = digest(receipt)
        self.room['stage']['name'] = 'New reviewed private version'
        self.local_file.write_text(json.dumps(self.room))
        runtime.saved = deepcopy(self.room)
        target = self.root / 'target' / 'audio-audit-page-numbers-v1'
        new_plan = build_audio_plan(self.room, self.binding, runtime.base_url)
        manifest = {'schemaVersion': AUDIO_INHERITANCE_SCHEMA, 'sourceAudioAuditDirectory': str(source),
            'sourcePlanSha256': digest(old_plan), 'sourceAuditSha256': digest(old_audit),
            'sourceSha256': old_plan['sourceSha256'], 'targetPlanSha256': digest(new_plan),
            'targetSourceSha256': new_plan['sourceSha256'], 'segments': [entry]}
        runtime.reset_mock()
        with self.assertRaisesRegex(ValueError, 'page_number_policy_required'):
            narrate_candidate(runtime, self.room, self.binding, target, self.store, audio_inheritance=manifest)
        original_audit = (source / 'audit.json').read_bytes()
        for changed_receipt in (False, True):
            altered = deepcopy(old_audit)
            proof = altered['segments'][0]['pageNumberEquivalence']
            if changed_receipt:
                foreign = {**proof['asrReceipt'], 'requestId': 'unrelated-asr'}
                altered['segments'][0]['pageNumberEquivalence'] = page_number_equivalence(text, foreign)
            else:
                proof['normalizedTextSha256'] = '0' * 64
            altered['sha256'] = digest({k: v for k, v in altered.items() if k != 'sha256'})
            (source / 'audit.json').write_text(json.dumps(altered))
            invalid = {**manifest, 'sourceAuditSha256': digest(altered)}
            with self.assertRaisesRegex(ValueError, 'evidence_changed|page_number_receipt_mismatch'):
                narrate_candidate(runtime, self.room, self.binding, target, self.store,
                                  audio_inheritance=invalid, allow_page_number_equivalence=True)
        (source / 'audit.json').write_bytes(original_audit)
        result = narrate_candidate(runtime, self.room, self.binding, target, self.store,
                                  audio_inheritance=manifest, allow_page_number_equivalence=True)
        self.assertEqual(result['segments'][0]['similarityBps'], 10000)
        self.assertEqual(result['segments'][0]['ttsRequestId'], segment['ttsRequestId'])
        self.assertEqual(result['segments'][0]['pageNumberEquivalence'], segment['pageNumberEquivalence'])
        runtime.start_formal_audio_tts.assert_not_called()
        runtime.start_formal_audio_asr.assert_not_called()
        runtime.download_formal_audio_tts.assert_not_called()
        self.assertEqual((source / 'audit.json').read_bytes(), original_audit)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.root / "classrooms"
        self.store.mkdir()
        self.output = self.root / "audio-audit"
        self.room = classroom()
        self.local_file = self.store / "synthetic-room.json"
        self.local_file.write_text(json.dumps(self.room), encoding="utf-8")
        self.binding = {key: manifest()[key] for key in
                        ("editionId", "revisionId", "gradeCode", "subject", "schoolSystem", "volume")}

    def runtime(self):
        runtime = Mock()
        runtime.base_url = "http://127.0.0.1:3100"
        runtime.get_formal_audio_tts.side_effect = missing()
        runtime.get_formal_audio_asr.side_effect = missing()
        audio = wav_bytes()
        runtime.start_formal_audio_tts.side_effect = lambda **payload: {
            "requestId": payload["request_id"], "status": "succeeded", "mimeType": "audio/wav",
            "audioSha256": hashlib.sha256(audio).hexdigest()}
        runtime.start_formal_audio_asr.side_effect = lambda **payload: {
            "requestId": payload["request_id"], "status": "succeeded", "transcript": "请看小猫。",
            "transcriptSha256": hashlib.sha256("请看小猫。".encode()).hexdigest(), "completionUsable": True}
        runtime.download_formal_audio_tts.return_value = audio
        runtime.saved = deepcopy(self.room)
        runtime.get_classroom.side_effect = lambda _id: deepcopy(runtime.saved)

        def save(value):
            runtime.saved = deepcopy(value)
            self.local_file.write_text(json.dumps(value), encoding="utf-8")
        runtime.save_preview_classroom.side_effect = save
        return runtime

    def narrate(self, runtime, **kwargs):
        return narrate_candidate(runtime, self.room, self.binding, self.output, self.store, **kwargs)

    def low_similarity(self, preceding=0):
        text = "新朋友来了，把它送到圆柱的家。"
        transcript = "新朋友来了，把他送到原住的家。"
        actions = [{"id": f"prior-{i}", "type": "speech", "text": "请看小猫。"} for i in range(preceding)]
        actions.append({"id": "cue-ug_game_cylinder_drag", "type": "speech", "text": text})
        self.room["scenes"][0]["actions"] = actions
        self.local_file.write_text(json.dumps(self.room), encoding="utf-8")
        runtime = self.runtime()
        def recognize(**payload):
            value = transcript if payload["action_id"] == actions[-1]["id"] else "请看小猫。"
            return {"requestId": payload["request_id"], "status": "succeeded", "transcript": value,
                    "transcriptSha256": hashlib.sha256(value.encode()).hexdigest(), "completionUsable": True}
        runtime.start_formal_audio_asr.side_effect = recognize
        with self.assertRaisesRegex(RuntimeError, "narration_asr_semantic_review_required_no_retry"):
            self.narrate(runtime)
        plan = json.loads((self.output / "plan.json").read_text())
        segment = json.loads((self.output / "audit.json").read_text())["segments"][-1]
        original_path = self.output / f"{segment['asrRequestId']}.json"
        receipt = json.loads(original_path.read_text())["receipt"]
        self.assertEqual(segment["similarityBps"], 7692)
        reconciliation = {"schemaVersion": ASR_RECONCILIATION_SCHEMA,
            "planSha256": digest(plan), "sourceSha256": plan["sourceSha256"], "segments": [{
                "sceneId": segment["sceneId"], "segmentId": segment["segmentId"],
                "originalAsrRequestId": segment["asrRequestId"], "audioSha256": segment["audioSha256"],
                "originalAsrReceiptSha256": digest(receipt), "originalSimilarityBps": 7692,
                "reason": ASR_RECONCILIATION_REASON}]}
        originals = {path: path.read_bytes() for path in self.output.glob("tbb*.json")}
        return runtime, reconciliation, originals

    def exact_recognition(self, **payload):
        text = "新朋友来了，把它送到圆柱的家。"
        return {"requestId": payload["request_id"], "status": "succeeded", "transcript": text,
                "transcriptSha256": hashlib.sha256(text.encode()).hexdigest(), "completionUsable": True}

    def inheritance(self, preceding=21):
        runtime, _, _ = self.low_similarity(preceding=preceding)
        source = self.output
        source_plan = json.loads((source / "plan.json").read_text())
        source_audit = json.loads((source / "audit.json").read_text())
        self.room = deepcopy(self.room)
        replacement = "请看看这个物品，再把它放到圆柱的小屋里。"
        self.room["scenes"][0]["actions"][-1]["text"] = replacement
        self.local_file.write_text(json.dumps(self.room), encoding="utf-8")
        runtime.saved = deepcopy(self.room)
        self.output = self.root / "audio-audit-v2"
        plan = build_audio_plan(self.room, self.binding, runtime.base_url)
        entries = []
        for segment in source_audit["segments"][:-1]:
            tts = json.loads((source / f"{segment['ttsRequestId']}.json").read_text())["receipt"]
            asr = json.loads((source / f"{segment['asrRequestId']}.json").read_text())["receipt"]
            entries.append({key: segment[key] for key in
                ("sceneId", "segmentId", "textSha256", "ttsRequestId", "asrRequestId", "audioSha256", "similarityBps")})
            entries[-1].update(ttsReceiptSha256=digest(tts), asrReceiptSha256=digest(asr))
        value = {"schemaVersion": AUDIO_INHERITANCE_SCHEMA, "sourceAudioAuditDirectory": str(source.resolve()),
            "sourcePlanSha256": digest(source_plan), "sourceAuditSha256": digest(source_audit),
            "sourceSha256": source_plan["sourceSha256"], "targetPlanSha256": digest(plan),
            "targetSourceSha256": plan["sourceSha256"], "segments": entries}
        def recognize(**payload):
            return {"requestId": payload["request_id"], "status": "succeeded", "transcript": replacement,
                    "transcriptSha256": hashlib.sha256(replacement.encode()).hexdigest(), "completionUsable": True}
        runtime.start_formal_audio_asr.side_effect = recognize
        original_files = {path.resolve(): path.read_bytes() for path in source.glob("*.json")}
        return runtime, value, original_files

    def two_source_inheritance(self):
        runtime, first, original_files = self.inheritance()
        placed = {"id": "cue-ug_game_cylinder_placed", "type": "speech", "text": "放好了，两个朋友都像圆柱。"}
        self.room["scenes"][0]["actions"].append(placed)
        self.local_file.write_text(json.dumps(self.room))
        runtime.saved = deepcopy(self.room)
        v2_plan = build_audio_plan(self.room, self.binding, runtime.base_url)
        first.update(targetPlanSha256=digest(v2_plan), targetSourceSha256=v2_plan["sourceSha256"])
        def recognize(**payload):
            text = ("放好了，两个朋友都上圆桌。" if payload["action_id"] == placed["id"]
                    else "请看看这个物品，再把它放到圆柱的小屋里。")
            return {"requestId": payload["request_id"], "status": "succeeded", "transcript": text,
                    "transcriptSha256": hashlib.sha256(text.encode()).hexdigest(), "completionUsable": True}
        runtime.start_formal_audio_asr.side_effect = recognize
        with self.assertRaisesRegex(RuntimeError, "narration_asr_semantic_review_required_no_retry"):
            self.narrate(runtime, audio_inheritance=first)
        source = self.output.resolve()
        source_audit = json.loads((source / "audit.json").read_text())
        self.assertEqual(source_audit["segments"][-1]["similarityBps"], 8181)
        self.room = deepcopy(self.room)
        replacement = "你把物品放好了。它们虽然长得不同，形状都像圆柱。"
        self.room["scenes"][0]["actions"][-1]["text"] = replacement
        self.local_file.write_text(json.dumps(self.room))
        runtime.saved = deepcopy(self.room)
        self.output = self.root / "audio-audit-v3"
        plan = build_audio_plan(self.room, self.binding, runtime.base_url)
        first.update(targetPlanSha256=digest(plan), targetSourceSha256=plan["sourceSha256"])
        segment = source_audit["segments"][21]
        self.assertNotIn("inheritedFrom", segment)
        entry = {key: segment[key] for key in ("sceneId", "segmentId", "textSha256",
            "ttsRequestId", "asrRequestId", "audioSha256", "similarityBps")}
        for kind in ("tts", "asr"):
            receipt = json.loads((source / f"{entry[kind+'RequestId']}.json").read_text())["receipt"]
            entry[kind+"ReceiptSha256"] = digest(receipt)
        second = {"schemaVersion": AUDIO_INHERITANCE_SCHEMA, "sourceAudioAuditDirectory": str(source),
            "sourcePlanSha256": digest(v2_plan), "sourceAuditSha256": digest(source_audit),
            "sourceSha256": v2_plan["sourceSha256"], "targetPlanSha256": digest(plan),
            "targetSourceSha256": plan["sourceSha256"], "segments": [entry]}
        def exact(**payload):
            return {"requestId": payload["request_id"], "status": "succeeded", "transcript": replacement,
                    "transcriptSha256": hashlib.sha256(replacement.encode()).hexdigest(), "completionUsable": True}
        runtime.start_formal_audio_asr.side_effect = exact
        original_files.update({path: path.read_bytes() for path in source.glob("*.json")})
        return runtime, [first, second], original_files

    def test_crash_after_post_then_404_never_reposts(self):
        runtime = Mock()
        runtime.get_formal_audio_tts.side_effect = missing()
        runtime.start_formal_audio_tts.side_effect = TimeoutError()
        path = self.root / "tts-checkpoint.json"
        payload = {"request_id": "request-1", "teacher_profile_sha256": "a" * 64}
        with self.assertRaises(TimeoutError):
            _external_once(runtime, path, "request-1", "tts", payload)
        self.assertEqual(json.loads(path.read_text())["state"], "dispatching")
        with self.assertRaisesRegex(RuntimeError, "audio_prior_dispatch_unresolved_no_retry"):
            _external_once(runtime, path, "request-1", "tts", payload)
        runtime.start_formal_audio_tts.assert_called_once()

    def test_dispatch_checkpoint_directory_is_synced_before_paid_post(self):
        runtime = Mock()
        runtime.get_formal_audio_tts.side_effect = missing()
        synced = []
        real_fsync = os.fsync
        def sync(descriptor):
            synced.append("directory" if stat.S_ISDIR(os.fstat(descriptor).st_mode) else "file")
            real_fsync(descriptor)
        def dispatch(**payload):
            self.assertEqual(synced[:2], ["file", "directory"])
            return {"requestId": "request-1", "status": "succeeded"}
        runtime.start_formal_audio_tts.side_effect = dispatch
        with patch("services.textbook_batch_audio.os.fsync", side_effect=sync):
            _external_once(runtime, self.root / "checkpoint.json", "request-1", "tts", {"request_id": "request-1"})

    def test_successful_receipt_reused_and_cross_bound_teacher_payload_rejected(self):
        runtime = Mock()
        runtime.get_formal_audio_tts.side_effect = missing()
        receipt = {"requestId": "request-1", "status": "succeeded", "audioSha256": "a" * 64}
        runtime.start_formal_audio_tts.return_value = receipt
        path = self.root / "tts-checkpoint.json"
        payload = {"request_id": "request-1", "teacher_profile_sha256": "b" * 64}
        self.assertEqual(_external_once(runtime, path, "request-1", "tts", payload), receipt)
        self.assertEqual(_external_once(runtime, path, "request-1", "tts", payload), receipt)
        runtime.start_formal_audio_tts.assert_called_once()
        runtime.get_formal_audio_tts.assert_called_once()
        with self.assertRaisesRegex(RuntimeError, "audio_request_identity_conflict"):
            _external_once(runtime, path, "request-1", "tts", {**payload, "teacher_profile_sha256": "c" * 64})

    def test_cached_receipt_for_another_request_is_rejected(self):
        runtime = Mock()
        payload = {"request_id": "request-1", "teacher_profile_sha256": "b" * 64}
        path = self.root / "tts-checkpoint.json"
        path.write_text(json.dumps({"requestId": "request-1", "requestPayloadSha256": digest(payload),
                                   "state": "succeeded", "receipt": {"requestId": "another-request",
                                   "status": "succeeded", "audioSha256": "a" * 64}}), encoding="utf-8")
        with self.assertRaises(RuntimeError):
            _external_once(runtime, path, "request-1", "tts", payload)
        runtime.start_formal_audio_tts.assert_not_called()

    def test_local_classroom_changed_blocks_before_any_paid_call(self):
        changed = deepcopy(self.room)
        changed["scenes"][0]["actions"][0]["text"] = "不同的讲解。"
        self.local_file.write_text(json.dumps(changed), encoding="utf-8")
        runtime = self.runtime()
        with self.assertRaisesRegex(RuntimeError, "runtime_classroom_changed"):
            self.narrate(runtime)
        runtime.get_formal_audio_tts.assert_not_called()
        runtime.start_formal_audio_tts.assert_not_called()

    def test_audio_hash_mismatch_stops_before_asr(self):
        runtime = self.runtime()
        runtime.download_formal_audio_tts.return_value = b"different bytes"
        with self.assertRaisesRegex(RuntimeError, "narration_audio_hash_changed"):
            self.narrate(runtime)
        runtime.start_formal_audio_asr.assert_not_called()
        runtime.save_preview_classroom.assert_not_called()

    def test_recovered_asr_without_ephemeral_transcript_never_reposts(self):
        runtime = self.runtime()
        runtime.get_formal_audio_asr.side_effect = lambda request_id: {
            "requestId": request_id, "status": "succeeded", "transcript": None,
            "transcriptSha256": "e" * 64, "completionUsable": False}
        with self.assertRaisesRegex(RuntimeError, "asr_transcript_recovery_required_no_retry"):
            self.narrate(runtime)
        with self.assertRaisesRegex(RuntimeError, "asr_transcript_recovery_required_no_retry"):
            self.narrate(runtime)
        runtime.start_formal_audio_asr.assert_not_called()
        runtime.start_formal_audio_tts.assert_called_once()
        runtime.save_preview_classroom.assert_not_called()

    def test_small_wav_full_run_reuses_successful_receipts_without_paid_replay(self):
        runtime = self.runtime()
        first = self.narrate(runtime)
        second = self.narrate(runtime)
        self.assertTrue(first["allSegmentsPassed"])
        self.assertEqual(second["completedSegments"], 1)
        self.assertFalse(second["publicationAllowed"])
        self.assertEqual(second["semanticPronunciationReview"], "pending")
        runtime.start_formal_audio_tts.assert_called_once()
        runtime.start_formal_audio_asr.assert_called_once()
        runtime.download_formal_audio_tts.assert_called_once()
        saved = runtime.saved["scenes"][0]["actions"][0]
        self.assertTrue(saved["audioUrl"].endswith(".wav"))
        self.assertEqual(saved["audioMetadata"]["providerId"], "qwen-tts")

    def test_explicit_asr_reconciliation_reuses_21_prior_segments_and_original_audio(self):
        runtime, reconciliation, originals = self.low_similarity(preceding=21)
        source_bytes = self.local_file.read_bytes()
        source_sha = digest(self.room)
        def dispatch(**payload):
            checkpoint = json.loads((self.output / f"{payload['request_id']}.json").read_text())
            self.assertEqual(checkpoint["state"], "dispatching")
            self.assertTrue((self.output / f"{payload['request_id']}.authorization.json").is_file())
            return self.exact_recognition(**payload)
        runtime.start_formal_audio_asr.reset_mock()
        runtime.start_formal_audio_asr.side_effect = dispatch
        result = self.narrate(runtime, asr_reconciliation=reconciliation)
        self.assertTrue(result["allSegmentsPassed"])
        self.assertEqual(result["completedSegments"], 22)
        self.assertEqual(runtime.start_formal_audio_tts.call_count, 22)
        runtime.start_formal_audio_asr.assert_called_once()
        self.assertEqual(runtime.download_formal_audio_tts.call_count, 22)
        segment = result["segments"][-1]
        review = segment["asrReconciliation"]
        self.assertEqual(segment["literalScoreBps"], 7692)
        self.assertEqual(segment["similarityBps"], 10000)
        self.assertEqual(segment["asrRequestId"], review["reconciliationAsrRequestId"])
        self.assertEqual(review["originalAsrRequestId"], reconciliation["segments"][0]["originalAsrRequestId"])
        self.assertEqual(review["reconciliationSimilarityBps"], 10000)
        self.assertEqual(result["semanticPronunciationReview"], "pending")
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original)
        self.assertEqual(digest(self.room), source_sha)
        # Runtime acquires audio only after the full audit succeeds; source input stays unchanged.
        self.assertNotEqual(self.local_file.read_bytes(), source_bytes)
        self.narrate(runtime, asr_reconciliation=deepcopy(reconciliation))
        runtime.start_formal_audio_asr.assert_called_once()
        self.assertEqual(runtime.start_formal_audio_tts.call_count, 22)

    def test_reconciliation_manifest_mismatches_stop_before_any_external_call(self):
        runtime, reconciliation, _ = self.low_similarity()
        cases = [("planSha256", "f" * 64), ("sourceSha256", "f" * 64),
                 ("sceneId", "another-scene"), ("segmentId", "another-segment"),
                 ("audioSha256", "f" * 64), ("originalAsrRequestId", "tbbasr_wrong"),
                 ("originalAsrReceiptSha256", "f" * 64), ("originalSimilarityBps", 7000),
                 ("reason", "heard_and_approved")]
        for key, value in cases:
            with self.subTest(key=key):
                invalid = deepcopy(reconciliation)
                (invalid if key in {"planSha256", "sourceSha256"} else invalid["segments"][0])[key] = value
                runtime.reset_mock()
                with self.assertRaises(ValueError):
                    self.narrate(runtime, asr_reconciliation=invalid)
                runtime.get_formal_audio_tts.assert_not_called()
                runtime.get_formal_audio_asr.assert_not_called()
                runtime.start_formal_audio_tts.assert_not_called()
                runtime.start_formal_audio_asr.assert_not_called()

    def test_duplicate_reconciliation_targets_and_extra_retry_nonce_are_rejected(self):
        runtime, reconciliation, _ = self.low_similarity()
        invalid = deepcopy(reconciliation)
        invalid["segments"].append(deepcopy(invalid["segments"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate_asr_reconciliation_segment"):
            self.narrate(runtime, asr_reconciliation=invalid)
        invalid = {**reconciliation, "retryNonce": "next-attempt"}
        with self.assertRaisesRegex(ValueError, "invalid_asr_reconciliation_manifest"):
            self.narrate(runtime, asr_reconciliation=invalid)
        self.assertEqual(runtime.start_formal_audio_asr.call_count, 1)

    def test_only_known_successful_original_asr_with_transcript_can_be_reconciled(self):
        runtime, reconciliation, originals = self.low_similarity()
        original_id = reconciliation["segments"][0]["originalAsrRequestId"]
        path = self.output / f"{original_id}.json"
        original = json.loads(path.read_text())
        for state in ("dispatching", "running", "ambiguous", "failed"):
            with self.subTest(state=state):
                invalid = {**original, "state": state}
                path.write_text(json.dumps(invalid))
                with self.assertRaisesRegex(ValueError, "asr_reconciliation_requires_known_success"):
                    self.narrate(runtime, asr_reconciliation=reconciliation)
        invalid = deepcopy(original)
        invalid["receipt"]["transcript"] = None
        invalid["receipt"]["completionUsable"] = False
        path.write_text(json.dumps(invalid))
        with self.assertRaisesRegex(ValueError, "asr_reconciliation_original_receipt_mismatch"):
            self.narrate(runtime, asr_reconciliation=reconciliation)
        path.write_bytes(originals[path])
        with patch("services.textbook_batch_audio.asr_similarity_bps", return_value=8500):
            with self.assertRaisesRegex(ValueError, "asr_reconciliation_requires_low_similarity"):
                self.narrate(runtime, asr_reconciliation=reconciliation)
        self.assertEqual(runtime.start_formal_audio_asr.call_count, 1)

    def test_original_audio_changed_or_missing_blocks_reconciliation(self):
        runtime, reconciliation, _ = self.low_similarity()
        segment = json.loads((self.output / "audit.json").read_text())["segments"][-1]
        path = self.store / self.room["id"] / "audio" / f"{segment['ttsRequestId']}.wav"
        path.write_bytes(b"different audio")
        with self.assertRaisesRegex(ValueError, "asr_reconciliation_original_audio_mismatch"):
            self.narrate(runtime, asr_reconciliation=reconciliation)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "asr_reconciliation_original_audio_mismatch"):
            self.narrate(runtime, asr_reconciliation=reconciliation)
        self.assertEqual(runtime.start_formal_audio_tts.call_count, 1)
        self.assertEqual(runtime.start_formal_audio_asr.call_count, 1)

    def test_reconciliation_below_threshold_stops_and_reuses_same_low_receipt(self):
        runtime, reconciliation, originals = self.low_similarity()
        for _ in range(2):
            with self.assertRaisesRegex(RuntimeError, "narration_asr_semantic_review_required_no_retry"):
                self.narrate(runtime, asr_reconciliation=deepcopy(reconciliation))
        self.assertEqual(runtime.start_formal_audio_tts.call_count, 1)
        self.assertEqual(runtime.start_formal_audio_asr.call_count, 2)
        segment = json.loads((self.output / "audit.json").read_text())["segments"][-1]
        self.assertEqual(segment["literalScoreBps"], 7692)
        self.assertEqual(segment["asrReconciliation"]["reconciliationSimilarityBps"], 7692)
        runtime.save_preview_classroom.assert_not_called()
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original)
        invalid = deepcopy(reconciliation)
        invalid["segments"][0]["originalAsrRequestId"] = segment["asrRequestId"]
        with self.assertRaisesRegex(ValueError, "asr_reconciliation_original_request_mismatch"):
            self.narrate(runtime, asr_reconciliation=invalid)

    def test_reconciliation_timeout_then_404_never_dispatches_second_recognition(self):
        runtime, reconciliation, _ = self.low_similarity()
        runtime.start_formal_audio_asr.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            self.narrate(runtime, asr_reconciliation=reconciliation)
        checkpoints = list(self.output.glob("tbbreasr_*.json"))
        checkpoint = next(path for path in checkpoints if not path.name.endswith(".authorization.json"))
        self.assertEqual(json.loads(checkpoint.read_text())["state"], "dispatching")
        with self.assertRaisesRegex(RuntimeError, "audio_prior_dispatch_unresolved_no_retry"):
            self.narrate(runtime, asr_reconciliation=reconciliation)
        self.assertEqual(runtime.start_formal_audio_asr.call_count, 2)
        self.assertEqual(runtime.start_formal_audio_tts.call_count, 1)

    def test_reconciliation_file_shape_is_checked_before_cli_configuration(self):
        path, _, _ = self.candidate()
        invalid = self.root / "invalid-reconciliation.json"
        invalid.write_text(json.dumps({"schemaVersion": ASR_RECONCILIATION_SCHEMA}))
        with patch("core.config.AppConfig.from_env") as config:
            with patch("sys.stderr", new=io.StringIO()):
                self.assertEqual(main(["--candidate-directory", str(path),
                                       "--asr-reconciliation-file", str(invalid)]), 1)
            config.assert_not_called()

    def test_reconciliation_file_is_loaded_and_cli_passes_explicit_manifest(self):
        runtime, reconciliation, _ = self.low_similarity()
        path, _, _ = self.candidate()
        approval = self.root / "review.json"
        approval.write_text(json.dumps(reconciliation))
        self.assertEqual(load_asr_reconciliation_file(approval), reconciliation)
        result = {"expectedSegments": 1, "completedSegments": 1, "allSegmentsPassed": True,
                  "semanticPronunciationReview": "pending", "interactiveStateNarrationReview": "pending"}
        with patch("core.config.AppConfig.from_env"):
            with patch("integrations.openmaic_full_runtime_client.OpenMaicFullRuntimeClient", return_value=runtime):
                with patch("services.textbook_batch_audio.narrate_candidate", return_value=result) as narrate:
                    with patch("sys.stdout", new=io.StringIO()):
                        self.assertEqual(main(["--candidate-directory", str(path),
                                               "--asr-reconciliation-file", str(approval)]), 0)
        self.assertEqual(narrate.call_args.kwargs["asr_reconciliation"], reconciliation)

    def test_21_passed_audio_segments_inherit_and_only_changed_segment_is_purchased(self):
        runtime, inheritance, original_files = self.inheritance()
        original_tts = runtime.start_formal_audio_tts.call_count
        original_asr = runtime.start_formal_audio_asr.call_count
        result = self.narrate(runtime, audio_inheritance=inheritance)
        self.assertTrue(result["allSegmentsPassed"])
        self.assertEqual(result["completedSegments"], 22)
        self.assertEqual(runtime.start_formal_audio_tts.call_count, original_tts + 1)
        self.assertEqual(runtime.start_formal_audio_asr.call_count, original_asr + 1)
        self.assertEqual(sum("inheritedFrom" in item for item in result["segments"]), 21)
        self.assertNotIn("inheritedFrom", result["segments"][-1])
        self.assertEqual(runtime.start_formal_audio_tts.call_args.kwargs["text"],
                         "请看看这个物品，再把它放到圆柱的小屋里。")
        self.assertEqual(runtime.start_formal_audio_tts.call_args.kwargs["classroom_content_sha256"],
                         inheritance["targetSourceSha256"])
        for old, new in zip(inheritance["segments"], result["segments"]):
            self.assertEqual(old["ttsRequestId"], new["ttsRequestId"])
            self.assertEqual(old["asrRequestId"], new["asrRequestId"])
            self.assertEqual(new["inheritedFrom"]["sourceSha256"], inheritance["sourceSha256"])
        self.narrate(runtime, audio_inheritance=deepcopy(inheritance))
        self.assertEqual(runtime.start_formal_audio_tts.call_count, original_tts + 1)
        self.assertEqual(runtime.start_formal_audio_asr.call_count, original_asr + 1)
        for path, content in original_files.items():
            self.assertEqual(path.read_bytes(), content)

    def test_omitted_or_changed_frozen_inheritance_never_rebuys_previous_segments(self):
        runtime, inheritance, _ = self.inheritance(preceding=2)
        self.narrate(runtime, audio_inheritance=inheritance)
        runtime.reset_mock()
        for value in (None, {**inheritance, "segments": inheritance["segments"][:-1]}):
            with self.assertRaisesRegex(RuntimeError, "frozen_audio_inheritance_manifest_required"):
                self.narrate(runtime, audio_inheritance=value)
        runtime.start_formal_audio_tts.assert_not_called()
        runtime.start_formal_audio_asr.assert_not_called()

    def test_inheritance_bad_last_entry_blocks_all_new_calls(self):
        runtime, inheritance, _ = self.inheritance(preceding=2)
        inheritance["segments"][-1]["asrReceiptSha256"] = "f" * 64
        runtime.reset_mock()
        with self.assertRaisesRegex(ValueError, "audio_inheritance_receipt_mismatch"):
            self.narrate(runtime, audio_inheritance=inheritance)
        runtime.start_formal_audio_tts.assert_not_called()
        runtime.start_formal_audio_asr.assert_not_called()

    def test_inheritance_refuses_changed_text_order_kind_binding_teacher_or_classroom(self):
        runtime, inheritance, _ = self.inheritance(preceding=2)
        saved_room = deepcopy(self.room)
        for mutation in ("text", "order", "kind", "binding", "teacher", "classroomId"):
            with self.subTest(mutation=mutation):
                self.room = deepcopy(saved_room)
                binding = deepcopy(self.binding)
                if mutation == "text":
                    self.room["scenes"][0]["actions"][0]["text"] = "多一个字。"
                if mutation == "order":
                    self.room["scenes"][0]["actions"][:2] = reversed(self.room["scenes"][0]["actions"][:2])
                if mutation == "kind":
                    self.room["scenes"][0]["actions"][0]["type"] = "annotation"
                if mutation == "binding":
                    binding["volume"] = "lower"
                if mutation == "classroomId":
                    self.room["id"] = self.room["stage"]["id"] = "different-room"
                plan = build_audio_plan(self.room, binding, runtime.base_url)
                if mutation == "teacher":
                    plan["teacher"]["voiceId"] = "different"
                altered = deepcopy(inheritance)
                altered.update(targetPlanSha256=digest(plan), targetSourceSha256=plan["sourceSha256"])
                from services.textbook_batch_audio import _inheritance_targets
                runtime.reset_mock()
                with self.assertRaises(ValueError):
                    _inheritance_targets(altered, plan, self.output,
                        self.store / "synthetic-room" / "audio", get_formal_subject_qwen_voice_identity("chinese"))
                runtime.start_formal_audio_tts.assert_not_called()
        self.room = saved_room

    def test_inheritance_refuses_low_segment_and_duplicate_or_unknown_manifest_fields(self):
        runtime, inheritance, _ = self.inheritance(preceding=2)
        source = Path(inheritance["sourceAudioAuditDirectory"])
        low = json.loads((source / "audit.json").read_text())["segments"][-1]
        entry = {key: low[key] for key in
            ("sceneId", "segmentId", "textSha256", "ttsRequestId", "asrRequestId", "audioSha256", "similarityBps")}
        entry.update(ttsReceiptSha256="a" * 64, asrReceiptSha256="b" * 64)
        invalid = deepcopy(inheritance)
        invalid["segments"].append(entry)
        with self.assertRaisesRegex(ValueError, "invalid_audio_inheritance_manifest"):
            self.narrate(runtime, audio_inheritance=invalid)
        invalid = deepcopy(inheritance)
        invalid["segments"].append(deepcopy(invalid["segments"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate_audio_inheritance_segment"):
            self.narrate(runtime, audio_inheritance=invalid)
        with self.assertRaisesRegex(ValueError, "invalid_audio_inheritance_manifest"):
            self.narrate(runtime, audio_inheritance={**inheritance, "automaticallyApprove": True})

    def test_low_last_source_segment_cannot_be_laundered_as_passed_in_inheritance(self):
        runtime, inheritance, _ = self.inheritance()
        source = Path(inheritance["sourceAudioAuditDirectory"])
        low = json.loads((source / "audit.json").read_text())["segments"][-1]
        # Keep the low text unchanged here, so failure proves receipt/score
        # eligibility rather than the changed-text guard of the real repair.
        self.room["scenes"][0]["actions"][-1]["text"] = "新朋友来了，把它送到圆柱的家。"
        self.room["stage"]["name"] = "Another private version"
        self.local_file.write_text(json.dumps(self.room))
        runtime.saved = deepcopy(self.room)
        plan = build_audio_plan(self.room, self.binding, runtime.base_url)
        inheritance.update(targetPlanSha256=digest(plan), targetSourceSha256=plan["sourceSha256"])
        entry = {key: low[key] for key in
            ("sceneId", "segmentId", "textSha256", "ttsRequestId", "asrRequestId", "audioSha256")}
        for kind in ("tts", "asr"):
            receipt = json.loads((source / f"{entry[kind+'RequestId']}.json").read_text())["receipt"]
            entry[kind+"ReceiptSha256"] = digest(receipt)
        entry["similarityBps"] = 10000
        inheritance["segments"].append(entry)
        runtime.reset_mock()
        with self.assertRaisesRegex(ValueError, "audio_inheritance_requires_original_passed_segment"):
            self.narrate(runtime, audio_inheritance=inheritance)
        runtime.start_formal_audio_tts.assert_not_called()
        runtime.start_formal_audio_asr.assert_not_called()

    def test_inheritance_source_audit_receipt_or_wav_changes_stop_before_dispatch(self):
        runtime, inheritance, original_files = self.inheritance(preceding=2)
        source = Path(inheritance["sourceAudioAuditDirectory"])
        audit_path = source / "audit.json"
        audit = json.loads(audit_path.read_text())
        audit["semanticPronunciationReview"] = "different"
        audit_path.write_text(json.dumps(audit))
        with self.assertRaisesRegex(ValueError, "audio_inheritance_source_evidence_mismatch"):
            self.narrate(runtime, audio_inheritance=inheritance)
        audit_path.write_bytes(original_files[audit_path])
        entry = inheritance["segments"][-1]
        receipt_path = source / f"{entry['asrRequestId']}.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["state"] = "ambiguous"
        receipt_path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, "asr_reconciliation_requires_known_success"):
            self.narrate(runtime, audio_inheritance=inheritance)
        receipt_path.write_bytes(original_files[receipt_path])
        wav_path = self.store / self.room["id"] / "audio" / f"{entry['ttsRequestId']}.wav"
        wav_path.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "audio_inheritance_audio_mismatch"):
            self.narrate(runtime, audio_inheritance=inheritance)
        self.assertEqual(runtime.start_formal_audio_tts.call_count, 3)
        self.assertEqual(runtime.start_formal_audio_asr.call_count, 3)

    def test_inheritance_cannot_hide_target_paid_dispatch_or_change_segment_checkpoint(self):
        runtime, inheritance, _ = self.inheritance(preceding=2)
        self.output.mkdir()
        plan = build_audio_plan(self.room, self.binding, runtime.base_url)
        target_id, _, _, _ = _segment_requests(plan, plan["workload"][0],
            get_formal_subject_qwen_voice_identity("chinese"))
        checkpoint = self.output / f"{target_id}.json"
        checkpoint.write_text(json.dumps({"state": "dispatching"}))
        with self.assertRaisesRegex(ValueError, "audio_inheritance_conflicts_with_target_dispatch"):
            self.narrate(runtime, audio_inheritance=inheritance)
        checkpoint.unlink()
        inherited_id = inheritance["segments"][-1]["ttsRequestId"]
        (self.output / f"{inherited_id}.inheritance.json").write_text(json.dumps({"changed": True}))
        with self.assertRaisesRegex(RuntimeError, "frozen_audio_inheritance_segment_changed"):
            self.narrate(runtime, audio_inheritance=inheritance)
        self.assertEqual(runtime.start_formal_audio_tts.call_count, 3)
        self.assertEqual(runtime.start_formal_audio_asr.call_count, 3)

    def test_audio_inheritance_cli_manifest_shape_checked_before_configuration(self):
        path, _, _ = self.candidate()
        invalid = self.root / "invalid-inheritance.json"
        invalid.write_text(json.dumps({"schemaVersion": AUDIO_INHERITANCE_SCHEMA}))
        with patch("core.config.AppConfig.from_env") as config:
            with patch("sys.stderr", new=io.StringIO()):
                self.assertEqual(main(["--candidate-directory", str(path),
                                       "--audio-inheritance-file", str(invalid)]), 1)
            config.assert_not_called()

    def test_audio_inheritance_file_loaded_and_cli_passed_without_implicit_approval(self):
        runtime, inheritance, _ = self.inheritance(preceding=2)
        path, _, _ = self.candidate()
        manifest_path = self.root / "inheritance.json"
        manifest_path.write_text(json.dumps(inheritance))
        self.assertEqual(load_audio_inheritance_file(manifest_path), inheritance)
        result = {"expectedSegments": 1, "completedSegments": 1, "allSegmentsPassed": True,
                  "semanticPronunciationReview": "pending", "interactiveStateNarrationReview": "pending"}
        with patch("core.config.AppConfig.from_env"):
            with patch("integrations.openmaic_full_runtime_client.OpenMaicFullRuntimeClient", return_value=runtime):
                with patch("services.textbook_batch_audio.narrate_candidate", return_value=result) as narrate:
                    with patch("sys.stdout", new=io.StringIO()):
                        self.assertEqual(main(["--candidate-directory", str(path),
                                               "--audio-inheritance-file", str(manifest_path)]), 0)
        self.assertEqual(narrate.call_args.kwargs["audio_inheritance"], inheritance)

    def test_two_sources_inherit_22_segments_and_only_changed_23_is_purchased(self):
        runtime, manifests, originals = self.two_source_inheritance()
        old_tts, old_asr = runtime.start_formal_audio_tts.call_count, runtime.start_formal_audio_asr.call_count
        result = self.narrate(runtime, audio_inheritance=manifests)
        self.assertTrue(result["allSegmentsPassed"])
        self.assertEqual(sum("inheritedFrom" in item for item in result["segments"]), 22)
        self.assertEqual(runtime.start_formal_audio_tts.call_count, old_tts + 1)
        self.assertEqual(runtime.start_formal_audio_asr.call_count, old_asr + 1)
        self.assertNotIn("inheritedFrom", result["segments"][22])
        self.assertEqual(result["segments"][21]["inheritedFrom"]["sourceSha256"], manifests[1]["sourceSha256"])
        reversed_manifests = deepcopy(list(reversed(manifests)))
        for manifest in reversed_manifests:
            manifest["segments"].reverse()
        self.narrate(runtime, audio_inheritance=reversed_manifests)
        self.assertEqual(runtime.start_formal_audio_tts.call_count, old_tts + 1)
        self.assertEqual(runtime.start_formal_audio_asr.call_count, old_asr + 1)
        self.assertEqual(normalize_audio_inheritance(manifests), normalize_audio_inheritance(reversed_manifests))
        for path, content in originals.items():
            self.assertEqual(path.read_bytes(), content)

    def test_frozen_multiple_inheritance_sources_cannot_be_omitted_or_modified(self):
        runtime, manifests, _ = self.two_source_inheritance()
        self.narrate(runtime, audio_inheritance=manifests)
        modified = deepcopy(manifests)
        modified[1]["sourceAuditSha256"] = "f" * 64
        runtime.reset_mock()
        for value in (None, manifests[:1], manifests[1:], modified):
            with self.subTest(value=value):
                with self.assertRaisesRegex(RuntimeError, "frozen_audio_inheritance_manifest_required"):
                    self.narrate(runtime, audio_inheritance=value)
        runtime.start_formal_audio_tts.assert_not_called()
        runtime.start_formal_audio_asr.assert_not_called()

    def test_overlapping_targets_across_sources_or_duplicate_file_are_rejected_before_dispatch(self):
        runtime, manifests, _ = self.two_source_inheritance()
        overlapping = deepcopy(manifests)
        overlapping[1]["segments"].append(deepcopy(overlapping[0]["segments"][0]))
        runtime.reset_mock()
        for value in (overlapping, [manifests[0], manifests[0]]):
            with self.assertRaisesRegex(ValueError, "overlapping_audio_inheritance_segments"):
                self.narrate(runtime, audio_inheritance=value)
        runtime.start_formal_audio_tts.assert_not_called()
        runtime.start_formal_audio_asr.assert_not_called()

    def test_all_sources_preflight_before_new_calls_and_unknown_target_is_not_hidden(self):
        runtime, manifests, _ = self.two_source_inheritance()
        corrupted = deepcopy(manifests)
        corrupted[1]["segments"][0]["asrReceiptSha256"] = "f" * 64
        runtime.reset_mock()
        with self.assertRaisesRegex(ValueError, "audio_inheritance_receipt_mismatch"):
            self.narrate(runtime, audio_inheritance=corrupted)
        self.output.mkdir(exist_ok=True)
        plan = build_audio_plan(self.room, self.binding, runtime.base_url)
        target_id, _, _, _ = _segment_requests(plan, plan["workload"][21],
            get_formal_subject_qwen_voice_identity("chinese"))
        (self.output / f"{target_id}.json").write_text(json.dumps({"state": "dispatching"}))
        with self.assertRaisesRegex(ValueError, "audio_inheritance_conflicts_with_target_dispatch"):
            self.narrate(runtime, audio_inheritance=manifests)
        runtime.start_formal_audio_tts.assert_not_called()
        runtime.start_formal_audio_asr.assert_not_called()

    def test_legacy_single_manifest_checkpoint_is_preserved_and_accepts_equivalent_list(self):
        runtime, inheritance, _ = self.inheritance(preceding=2)
        self.output.mkdir()
        path = self.output / "inheritance-manifest.json"
        path.write_text(json.dumps(inheritance))
        original = path.read_bytes()
        self.narrate(runtime, audio_inheritance=inheritance)
        self.narrate(runtime, audio_inheritance=[inheritance])
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(runtime.start_formal_audio_tts.call_count, 4)
        self.assertEqual(runtime.start_formal_audio_asr.call_count, 4)

    def test_cli_repeatable_audio_inheritance_passes_complete_set(self):
        runtime, manifests, _ = self.two_source_inheritance()
        path, _, _ = self.candidate()
        paths = [self.root / f"inheritance-{index}.json" for index in range(2)]
        for manifest_path, value in zip(paths, manifests):
            manifest_path.write_text(json.dumps(value))
        result = {"expectedSegments": 23, "completedSegments": 23, "allSegmentsPassed": True,
                  "semanticPronunciationReview": "pending", "interactiveStateNarrationReview": "pending"}
        with patch("core.config.AppConfig.from_env"):
            with patch("integrations.openmaic_full_runtime_client.OpenMaicFullRuntimeClient", return_value=runtime):
                with patch("services.textbook_batch_audio.narrate_candidate", return_value=result) as narrate:
                    with patch("sys.stdout", new=io.StringIO()):
                        self.assertEqual(main(["--candidate-directory", str(path),
                            "--audio-inheritance-file", str(paths[0]),
                            "--audio-inheritance-file", str(paths[1])]), 0)
        self.assertEqual(narrate.call_args.kwargs["audio_inheritance"], manifests)

    def test_frozen_teacher_changed_is_rejected_before_paid_calls(self):
        runtime = self.runtime()
        self.narrate(runtime)
        runtime.start_formal_audio_tts.reset_mock()
        voice = get_formal_subject_qwen_voice_identity("chinese")
        changed = replace(voice, teacher_profile_hash="f" * 64, voice_id="different-voice")
        with patch("services.textbook_batch_audio.get_formal_subject_qwen_voice_identity", return_value=changed):
            with self.assertRaisesRegex(RuntimeError, "frozen_audio_plan_changed"):
                self.narrate(runtime)
        runtime.start_formal_audio_tts.assert_not_called()

    def test_readback_dropping_audio_is_not_a_success(self):
        runtime = self.runtime()
        runtime.save_preview_classroom.side_effect = lambda value: None
        with self.assertRaises(RuntimeError):
            self.narrate(runtime)
        if (self.output / "audit.json").exists():
            self.assertFalse(json.loads((self.output / "audit.json").read_text())["allSegmentsPassed"])

    def test_duplicate_narration_segments_are_rejected(self):
        invalid = self.room
        invalid["scenes"][0]["actions"].append(deepcopy(invalid["scenes"][0]["actions"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate_narration_segment"):
            narration_workload(invalid)

    def test_interactive_cues_are_prerecorded_saved_and_reused(self):
        self.room["scenes"].append({"id": "game-1", "type": "interactive", "actions": [], "content": {
            "html": activity([{"id": "find-cat", "text": "请看小猫。"}])}})
        self.local_file.write_text(json.dumps(self.room), encoding="utf-8")
        runtime = self.runtime()
        result = self.narrate(runtime)
        self.assertTrue(result["allSegmentsPassed"])
        self.assertEqual(result["interactiveCuesCompleted"], 1)
        self.assertIn('id="mira-pre-recorded-audio"', runtime.saved["scenes"][1]["content"]["html"])
        self.narrate(runtime)
        self.assertEqual(runtime.start_formal_audio_tts.call_count, 2)
        self.assertEqual(runtime.start_formal_audio_asr.call_count, 2)

    def test_browser_speech_blocks_before_any_paid_audio(self):
        self.room["scenes"].append({"id": "bad-game", "type": "interactive", "actions": [], "content": {
            "html": "<script>window.speechSynthesis.speak(x)</script>"}})
        self.local_file.write_text(json.dumps(self.room), encoding="utf-8")
        runtime = self.runtime()
        with self.assertRaisesRegex(ValueError, "browser_speech"):
            self.narrate(runtime)
        runtime.start_formal_audio_tts.assert_not_called()

    def test_quiz_question_and_feedback_are_separate_narration_segments(self):
        value = self.room
        value["scenes"].append({"id": "quiz-1", "type": "quiz", "actions": [], "content": {
            "questions": [{"id": "question-1", "question": "指一指小猫。", "analysis": "这是一只小猫。"}]}})
        workload = narration_workload(value)
        self.assertEqual([item["kind"] for item in workload], ["speech", "prompt", "feedback"])
        self.assertEqual([item.get("questionId") for item in workload[1:]], ["question-1", "question-1"])

    def candidate(self):
        path = self.root / ("a" * 64)
        path.mkdir()
        book = manifest()
        frozen = {"schemaVersion": INPUT_SCHEMA, "taskId": path.name, "binding": self.binding,
                  "kind": "book_exploration",
                  "manifest": book, "manifestSha256": digest(book),
                  "teachingProfile": teaching_profile("primary_1"),
                  "publicationAllowed": False, "studentDeliveryAllowed": False}
        frozen["inputSha256"] = digest(frozen)
        state = {"schemaVersion": "mira.textbook.private-batch-generation-state.v1",
                 "taskId": path.name, "inputSha256": frozen["inputSha256"], "status": "generated_needs_review",
                 "publicationAllowed": False, "studentDeliveryAllowed": False,
                 "classroomId": self.room["id"], "classroomSha256": digest(self.room),
                 "runtimeOrigin": "http://127.0.0.1:3100"}
        for name, value in (("input.json", frozen), ("state.json", state), ("classroom.json", self.room)):
            (path / name).write_text(json.dumps(value), encoding="utf-8")
        return path, frozen, state

    def test_cli_candidate_hash_and_exact_scope_checked_before_configuration(self):
        path, frozen, state = self.candidate()
        self.assertEqual(load_candidate(path)[0]["binding"], self.binding)
        altered = deepcopy(self.room)
        altered["scenes"][0]["actions"][0]["text"] = "Changed after generation"
        (path / "classroom.json").write_text(json.dumps(altered), encoding="utf-8")
        with patch("core.config.AppConfig.from_env") as config:
            with patch("sys.stderr", new=io.StringIO()):
                self.assertEqual(main(["--candidate-directory", str(path)]), 1)
            config.assert_not_called()

        (path / "classroom.json").write_text(json.dumps(self.room), encoding="utf-8")
        frozen["binding"] = {**frozen["binding"], "subject": "math"}
        frozen["inputSha256"] = digest({key: value for key, value in frozen.items() if key != "inputSha256"})
        state["inputSha256"] = frozen["inputSha256"]
        (path / "input.json").write_text(json.dumps(frozen), encoding="utf-8")
        (path / "state.json").write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "candidate_textbook_scope_or_grade_changed"):
            load_candidate(path)

    def test_legacy_frozen_portrait_requires_real_runtime_portrait_before_paid_calls(self):
        path, frozen, state = self.candidate()
        voice = get_formal_subject_qwen_voice_identity("chinese")
        contract = get_formal_runtime_teacher_contract("chinese")
        teacher = voice.to_target_payload()
        teacher["avatarPath"] = get_teacher_profile(voice.teacher_profile_id, voice.teacher_profile_version).avatar_path
        frozen["authoringPrompt"] = {"version": "2"}
        frozen["runtimeBatchContext"] = {"teacher": teacher, "taskId": path.name,
            "binding": self.binding, "kind": "book_exploration", "gradeCode": "primary_1", "subject": "chinese"}
        frozen["inputSha256"] = digest({key: value for key, value in frozen.items() if key != "inputSha256"})
        state["inputSha256"] = frozen["inputSha256"]
        room = deepcopy(self.room)
        room["stage"]["generatedAgentConfigs"] = [{"id": "teacher-1", "role": "teacher",
            "name": teacher["teacherName"], "avatar": contract["runtime"]["avatar"],
            "teacherProfile": teacher["teacherProfile"], "voiceConfig": contract["runtime"]["voiceConfig"]}]
        state["classroomSha256"] = digest(room)
        for name, value in (("input.json", frozen), ("state.json", state), ("classroom.json", room)):
            (path / name).write_text(json.dumps(value))
        load_candidate(path)
        room["stage"]["generatedAgentConfigs"][0]["avatar"] = teacher["avatarPath"]
        state["classroomSha256"] = digest(room)
        (path / "classroom.json").write_text(json.dumps(room))
        (path / "state.json").write_text(json.dumps(state))
        with patch("core.config.AppConfig.from_env") as config:
            with patch("sys.stderr", new=io.StringIO()):
                self.assertEqual(main(["--candidate-directory", str(path)]), 1)
            config.assert_not_called()

        # The new presentation prompt must retain the same pre-provider
        # teacher fence rather than accidentally falling through the v2 gate.
        frozen["authoringPrompt"] = {"version": "3"}
        frozen["runtimeBatchContext"]["teacher"]["avatarPath"] = contract["runtime"]["avatar"]
        frozen["inputSha256"] = digest({key: value for key, value in frozen.items() if key != "inputSha256"})
        state["inputSha256"] = frozen["inputSha256"]
        room["stage"]["generatedAgentConfigs"][0]["avatar"] = contract["runtime"]["avatar"]
        state["classroomSha256"] = digest(room)
        for name, value in (("input.json", frozen), ("state.json", state), ("classroom.json", room)):
            (path / name).write_text(json.dumps(value))
        load_candidate(path)
        room["stage"]["generatedAgentConfigs"][0]["name"] = "Wrong teacher"
        state["classroomSha256"] = digest(room)
        (path / "classroom.json").write_text(json.dumps(room))
        (path / "state.json").write_text(json.dumps(state))
        with patch("core.config.AppConfig.from_env") as config:
            with patch("sys.stderr", new=io.StringIO()):
                self.assertEqual(main(["--candidate-directory", str(path)]), 1)
            config.assert_not_called()


if __name__ == "__main__":
    unittest.main()
