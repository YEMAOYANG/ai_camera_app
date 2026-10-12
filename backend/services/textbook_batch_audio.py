"""Durable Qwen narration and ASR for saved, private batch candidates.

No course approval or publication. Every external synthesis/recognition is
checkpointed before dispatch; an unknown outcome is reconciled, never resent.
"""
from copy import deepcopy
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlparse
import wave

from content.teacher_profiles import get_formal_subject_qwen_voice_identity
from content.textbook_audio_language import ENGLISH_AUTO_LANGUAGE_OPTION, ENGLISH_AUTO_LANGUAGE_POLICY
from content.textbook_catalog import digest
from content.textbook_interactive_narration import (AUDIO_BLOCK, bind_interactive_audio,
                                                   interactive_cues, without_audio_helper)
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError
from services.learning_media_materialization_service import asr_similarity_bps
from content.textbook_number_spelling import page_number_equivalence, validate_page_number_equivalence


ASR_RECONCILIATION_SCHEMA = "mira.textbook.batch-asr-reconciliation.v1"
ASR_RECONCILIATION_REASON = "known_successful_but_low_similarity"
AUDIO_INHERITANCE_SCHEMA = "mira.textbook.batch-audio-inheritance.v1"
AUDIO_CLONE_INHERITANCE_SCHEMA = "mira.textbook.batch-audio-inheritance.v2"
AUDIO_INSERTION_CLONE_SCHEMA = "mira.textbook.batch-audio-inheritance.v3"
AUDIO_SCENE_INSERTION_CLONE_SCHEMA = "mira.textbook.batch-audio-inheritance.v4"
AUDIO_INHERITANCE_SET_SCHEMA = "mira.textbook.batch-audio-inheritance-set.v1"


def _plan_uses_english_auto(plan):
    if plan.get("schemaVersion") == "mira.textbook.batch-audio.v1":
        if "providerLanguagePolicy" in plan or "providerLanguagePolicySha256" in plan:
            raise ValueError("legacy_audio_plan_cannot_select_language_policy")
        return False
    if (plan.get("schemaVersion") != "mira.textbook.batch-audio.v2"
            or plan.get("binding", {}).get("subject") != "english"
            or plan.get("providerLanguagePolicy") != ENGLISH_AUTO_LANGUAGE_POLICY
            or plan.get("providerLanguagePolicySha256") != digest(ENGLISH_AUTO_LANGUAGE_POLICY)):
        raise ValueError("invalid_textbook_audio_language_policy")
    return True


def _asr_request_id(plan, tts_id, audio_hash):
    return ("tbbasr2_" if _plan_uses_english_auto(plan) else "tbbasr_") + digest(
        {"tts": tts_id, "audio": audio_hash})


def audio_language_policy_from_plan(plan):
    """Validate the saved version; never infer or upgrade a legacy plan."""
    return ENGLISH_AUTO_LANGUAGE_OPTION if _plan_uses_english_auto(plan) else None


def validate_asr_reconciliation(value):
    """An explicit, exact request for one recognition of already known audio."""
    if (not isinstance(value, dict) or set(value) != {
            "schemaVersion", "planSha256", "sourceSha256", "segments"}
            or value.get("schemaVersion") != ASR_RECONCILIATION_SCHEMA
            or not isinstance(value.get("segments"), list) or not 1 <= len(value["segments"]) <= 240):
        raise ValueError("invalid_asr_reconciliation_manifest")
    for key in ("planSha256", "sourceSha256"):
        if not isinstance(value[key], str) or not re.fullmatch(r"[0-9a-f]{64}", value[key]):
            raise ValueError("invalid_asr_reconciliation_manifest")
    seen = set()
    for entry in value["segments"]:
        if (not isinstance(entry, dict) or set(entry) != {
                "sceneId", "segmentId", "originalAsrRequestId", "audioSha256",
                "originalAsrReceiptSha256", "originalSimilarityBps", "reason"}
                or entry.get("reason") != ASR_RECONCILIATION_REASON
                or type(entry.get("originalSimilarityBps")) is not int
                or not 0 <= entry["originalSimilarityBps"] < 8500):
            raise ValueError("invalid_asr_reconciliation_manifest")
        for key, limit in (("sceneId", 128), ("segmentId", 200), ("originalAsrRequestId", 128)):
            if not isinstance(entry[key], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1," + str(limit) + "}", entry[key]):
                raise ValueError("invalid_asr_reconciliation_manifest")
        for key in ("audioSha256", "originalAsrReceiptSha256"):
            if not isinstance(entry[key], str) or not re.fullmatch(r"[0-9a-f]{64}", entry[key]):
                raise ValueError("invalid_asr_reconciliation_manifest")
        identity = entry["sceneId"], entry["segmentId"]
        if identity in seen:
            raise ValueError("duplicate_asr_reconciliation_segment")
        seen.add(identity)
    return value


def load_asr_reconciliation_file(path):
    return validate_asr_reconciliation(json.loads(Path(path).read_text(encoding="utf-8")))


def validate_audio_inheritance(value):
    clone = isinstance(value, dict) and value.get("schemaVersion") in {
        AUDIO_CLONE_INHERITANCE_SCHEMA, AUDIO_INSERTION_CLONE_SCHEMA, AUDIO_SCENE_INSERTION_CLONE_SCHEMA}
    keys = {"schemaVersion", "sourceAudioAuditDirectory",
            "sourcePlanSha256", "sourceAuditSha256", "sourceSha256", "targetPlanSha256",
            "targetSourceSha256", "segments"}
    if clone:
        keys |= {"taskId", "sourceCandidateDirectory", "targetCandidateDirectory"}
    if (not isinstance(value, dict) or set(value) != keys
            or value.get("schemaVersion") not in {AUDIO_INHERITANCE_SCHEMA, AUDIO_CLONE_INHERITANCE_SCHEMA, AUDIO_INSERTION_CLONE_SCHEMA, AUDIO_SCENE_INSERTION_CLONE_SCHEMA}
            or not isinstance(value.get("sourceAudioAuditDirectory"), str)
            or not Path(value["sourceAudioAuditDirectory"]).is_absolute()
            or str(Path(value["sourceAudioAuditDirectory"]).resolve()) != value["sourceAudioAuditDirectory"]
            or not isinstance(value.get("segments"), list) or not 1 <= len(value["segments"]) <= 240):
        raise ValueError("invalid_audio_inheritance_manifest")
    if clone:
        if not isinstance(value["taskId"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["taskId"]):
            raise ValueError("invalid_audio_clone_task_identity")
        for key in ("sourceCandidateDirectory", "targetCandidateDirectory"):
            if (not isinstance(value[key], str) or not Path(value[key]).is_absolute()
                    or str(Path(value[key]).resolve()) != value[key]):
                raise ValueError("invalid_audio_clone_candidate_path")
    for key in ("sourcePlanSha256", "sourceAuditSha256", "sourceSha256", "targetPlanSha256", "targetSourceSha256"):
        if not isinstance(value[key], str) or not re.fullmatch(r"[0-9a-f]{64}", value[key]):
            raise ValueError("invalid_audio_inheritance_manifest")
    seen = set()
    for entry in value["segments"]:
        if (not isinstance(entry, dict) or set(entry) != {"sceneId", "segmentId", "textSha256",
                "ttsRequestId", "asrRequestId", "audioSha256", "ttsReceiptSha256", "asrReceiptSha256",
                "similarityBps"}
                or type(entry.get("similarityBps")) is not int or not 8500 <= entry["similarityBps"] <= 10000):
            raise ValueError("invalid_audio_inheritance_manifest")
        for key, limit in (("sceneId", 128), ("segmentId", 200), ("ttsRequestId", 128), ("asrRequestId", 128)):
            if not isinstance(entry[key], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1," + str(limit) + "}", entry[key]):
                raise ValueError("invalid_audio_inheritance_manifest")
        for key in ("textSha256", "audioSha256", "ttsReceiptSha256", "asrReceiptSha256"):
            if not isinstance(entry[key], str) or not re.fullmatch(r"[0-9a-f]{64}", entry[key]):
                raise ValueError("invalid_audio_inheritance_manifest")
        identity = entry["sceneId"], entry["segmentId"]
        if identity in seen:
            raise ValueError("duplicate_audio_inheritance_segment")
        seen.add(identity)
    return value


def load_audio_inheritance_file(path):
    return validate_audio_inheritance(json.loads(Path(path).read_text(encoding="utf-8")))


def normalize_audio_inheritance(value):
    """Freeze the complete set independently of file and segment ordering."""
    if value is None:
        return None
    if isinstance(value, dict) and value.get("schemaVersion") == AUDIO_INHERITANCE_SET_SCHEMA:
        if set(value) != {"schemaVersion", "manifests"}:
            raise ValueError("invalid_audio_inheritance_set")
        values = value["manifests"]
    else:
        values = value if isinstance(value, list) else [value]
    if not isinstance(values, list) or not 1 <= len(values) <= 240:
        raise ValueError("invalid_audio_inheritance_set")
    normalized, seen = [], set()
    for manifest in values:
        validate_audio_inheritance(manifest)
        manifest = deepcopy(manifest)
        manifest["segments"].sort(key=lambda entry: (entry["sceneId"], entry["segmentId"]))
        for entry in manifest["segments"]:
            key = entry["sceneId"], entry["segmentId"]
            if key in seen:
                raise ValueError("overlapping_audio_inheritance_segments")
            seen.add(key)
        normalized.append(manifest)
    if len(seen) > 240:
        raise ValueError("invalid_audio_inheritance_set")
    normalized.sort(key=digest)
    return {"schemaVersion": AUDIO_INHERITANCE_SET_SCHEMA, "manifests": normalized}


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".audio-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(name).unlink(missing_ok=True)


def narration_workload(classroom):
    """Speech, quiz instructions and every finite interactive teacher cue."""
    workload = []
    for index, scene in enumerate(classroom.get("scenes", [])):
        scene_id = scene.get("id")
        if not isinstance(scene_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", scene_id):
            raise ValueError("invalid_scene_identity")
        for action in scene.get("actions", []):
            if action.get("type") == "speech":
                workload.append({"sceneId": scene_id, "sceneOrder": index,
                                 "id": action.get("id"), "kind": "speech", "text": action.get("text", "")})
        if scene.get("type") == "quiz":
            for question in scene.get("content", {}).get("questions", []):
                qid = question.get("id")
                for suffix, field in (("prompt", "question"), ("feedback", "analysis")):
                    if question.get(field):
                        workload.append({"sceneId": scene_id, "sceneOrder": index,
                                         "id": f"quiz-{qid}-{suffix}", "questionId": qid,
                                         "kind": suffix, "text": question[field]})
        if scene.get("type") == "interactive":
            html = scene.get("content", {}).get("html", "")
            for cue in interactive_cues(html):
                workload.append({"sceneId": scene_id, "sceneOrder": index,
                                 "id": "cue-" + cue["id"], "cueId": cue["id"],
                                 "kind": "interactive", "text": cue["text"]})
    if not 1 <= len(workload) <= 240:
        raise ValueError("invalid_narration_workload")
    identities = set()
    for item in workload:
        if (not isinstance(item["id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", item["id"])
                or not isinstance(item["text"], str) or not 0 < len(item["text"].strip()) <= 4000):
            raise ValueError("invalid_narration_segment")
        item["text"] = item["text"].strip()
        identity = item["sceneId"], item["id"]
        if identity in identities:
            raise ValueError("duplicate_narration_segment")
        identities.add(identity)
    return workload


def _external_once(runtime, checkpoint, request_id, operation, payload):
    previous = json.loads(checkpoint.read_text()) if checkpoint.exists() else None
    if previous and (previous.get("requestId") != request_id
                     or previous.get("requestPayloadSha256") != digest(payload)):
        raise RuntimeError("audio_request_identity_conflict")
    if previous and previous.get("receipt", {}).get("status") == "succeeded":
        if previous["receipt"].get("requestId") != request_id:
            raise RuntimeError("audio_receipt_identity_conflict")
        return previous["receipt"]
    getter = getattr(runtime, f"get_formal_audio_{operation}")
    try:
        receipt = getter(request_id)
    except OpenMaicFullRuntimeError as exc:
        if exc.status_code != 404:
            raise
        if previous:
            raise RuntimeError("audio_prior_dispatch_unresolved_no_retry") from exc
        save_json(checkpoint, {"requestId": request_id, "requestPayloadSha256": digest(payload),
                               "state": "dispatching"})
        # A crash/timeout here leaves dispatching. Next run only queries it.
        receipt = getattr(runtime, f"start_formal_audio_{operation}")(**payload)
    if receipt.get("requestId") != request_id:
        raise RuntimeError("audio_receipt_identity_conflict")
    save_json(checkpoint, {"requestId": request_id, "requestPayloadSha256": digest(payload),
                           "state": receipt.get("status"), "receipt": receipt})
    if receipt.get("status") != "succeeded":
        raise RuntimeError(f"audio_{operation}_{receipt.get('status', 'unknown')}_no_retry")
    return receipt


def _audio_bindings(classroom):
    """Readback must preserve the audio, not just unchanged teaching text."""
    bindings = {}
    for scene in classroom.get("scenes", []):
        if scene.get("type") == "interactive":
            bindings[(scene.get("id"), "interactive")] = AUDIO_BLOCK.findall(
                scene.get("content", {}).get("html", ""))
        for action in scene.get("actions", []):
            if action.get("type") == "speech":
                bindings[(scene.get("id"), "speech", action.get("id"))] = {
                    key: action.get(key) for key in ("audioId", "audioUrl", "audioMetadata")}
        for question in scene.get("content", {}).get("questions", []):
            bindings[(scene.get("id"), "quiz", question.get("id"))] = {
                key: question.get(key) for key in ("questionAudioUrl", "feedbackAudioUrl")}
    return bindings


def _segment_requests(plan, item, teacher):
    tts_id = ("tbbtts2_" if _plan_uses_english_auto(plan) else "tbbtts_") + digest(
        {"plan": digest(plan), "segment": item})
    identity = {"classroom_id": plan["classroomId"], "classroom_content_sha256": plan["sourceSha256"],
                "subject": plan["binding"]["subject"], "teacher_profile_id": teacher.teacher_profile_id,
                "teacher_profile_version": teacher.teacher_profile_version,
                "teacher_profile_sha256": teacher.teacher_profile_hash,
                "teacher_gender": teacher.teacher_gender, "scene_id": item["sceneId"],
                "scene_order": item["sceneOrder"], "action_id": item["id"],
                "narration_segment_id": item["id"]}
    text_hash = hashlib.sha256(item["text"].encode()).hexdigest()
    return tts_id, identity, text_hash, {
        **identity, "request_id": tts_id, "text": item["text"], "text_sha256": text_hash}


def _known_success(output, request_id, payload):
    path = output / f"{request_id}.json"
    if not path.is_file():
        raise ValueError("asr_reconciliation_requires_known_success")
    previous = json.loads(path.read_text())
    receipt = previous.get("receipt", {})
    if (previous.get("requestId") != request_id or previous.get("requestPayloadSha256") != digest(payload)
            or previous.get("state") != "succeeded" or receipt.get("status") != "succeeded"
            or receipt.get("requestId") != request_id):
        raise ValueError("asr_reconciliation_requires_known_success")
    return receipt


def _reconciliation_targets(value, plan, output, media, teacher):
    """Preflight every explicit entry before any new paid operation can start."""
    if value is None:
        return {}
    validate_asr_reconciliation(value)
    if value["planSha256"] != digest(plan) or value["sourceSha256"] != plan["sourceSha256"]:
        raise ValueError("asr_reconciliation_plan_or_source_mismatch")
    workload = {(item["sceneId"], item["id"]): item for item in plan["workload"]}
    targets = {}
    for entry in value["segments"]:
        key = entry["sceneId"], entry["segmentId"]
        if key not in workload:
            raise ValueError("asr_reconciliation_segment_mismatch")
        item = workload[key]
        tts_id, identity, _, tts_payload = _segment_requests(plan, item, teacher)
        tts = _known_success(output, tts_id, tts_payload)
        if tts.get("audioSha256") != entry["audioSha256"]:
            raise ValueError("asr_reconciliation_audio_mismatch")
        asr_id = _asr_request_id(plan, tts_id, tts["audioSha256"])
        if entry["originalAsrRequestId"] != asr_id:
            raise ValueError("asr_reconciliation_original_request_mismatch")
        asr = _known_success(output, asr_id, {
            **identity, "request_id": asr_id, "tts_request_id": tts_id, "audio_sha256": tts["audioSha256"]})
        transcript = asr.get("transcript")
        if (not isinstance(transcript, str) or not transcript.strip()
                or asr.get("transcriptSha256") != hashlib.sha256(transcript.encode()).hexdigest()
                or digest(asr) != entry["originalAsrReceiptSha256"]):
            raise ValueError("asr_reconciliation_original_receipt_mismatch")
        score = asr_similarity_bps(item["text"], transcript)
        if score >= 8500 or score != entry["originalSimilarityBps"]:
            raise ValueError("asr_reconciliation_requires_low_similarity")
        audio_path = media / f"{tts_id}.wav"
        if not audio_path.is_file() or hashlib.sha256(audio_path.read_bytes()).hexdigest() != entry["audioSha256"]:
            raise ValueError("asr_reconciliation_original_audio_mismatch")
        # One permanent slot per original ASR. No filename, reason, timestamp,
        # transcript or review score can create another recognition identity.
        request_id = ("tbbreasr2_" if _plan_uses_english_auto(plan) else "tbbreasr_") + digest({"purpose": ASR_RECONCILIATION_SCHEMA,
            "planSha256": digest(plan), "sourceSha256": plan["sourceSha256"],
            "sceneId": entry["sceneId"], "segmentId": entry["segmentId"],
            "originalAsrRequestId": asr_id, "audioSha256": entry["audioSha256"]})
        targets[key] = {"requestId": request_id, "authorization": {
            "schemaVersion": ASR_RECONCILIATION_SCHEMA, "planSha256": digest(plan),
            "sourceSha256": plan["sourceSha256"], "segment": deepcopy(entry)}}
    return targets


def build_audio_plan(classroom, binding, runtime_origin, *, audio_language_policy=None):
    """Provider-free immutable plan used by explicit inheritance operators."""
    from services.textbook_preview_audio import core_content
    value = core_content(classroom)
    for scene in value.get("scenes", []):
        if scene.get("type") == "interactive" and isinstance(scene.get("content", {}).get("html"), str):
            scene["content"]["html"] = without_audio_helper(scene["content"]["html"])
        for question in scene.get("content", {}).get("questions", []):
            question.pop("questionAudioUrl", None)
            question.pop("feedbackAudioUrl", None)
    plan = {"schemaVersion": "mira.textbook.batch-audio.v1", "binding": binding,
            "classroomId": classroom["id"], "sourceSha256": digest(classroom),
            "coreSha256": digest(value),
            "teacher": get_formal_subject_qwen_voice_identity(binding["subject"]).to_target_payload(),
            "workload": narration_workload(classroom), "runtimeOrigin": runtime_origin, "publicationAllowed": False}
    if audio_language_policy is not None:
        if audio_language_policy != ENGLISH_AUTO_LANGUAGE_OPTION or binding["subject"] != "english":
            raise ValueError("english_auto_language_policy_requires_english_subject")
        plan.update(schemaVersion="mira.textbook.batch-audio.v2",
                    providerLanguagePolicy=deepcopy(ENGLISH_AUTO_LANGUAGE_POLICY),
                    providerLanguagePolicySha256=digest(ENGLISH_AUTO_LANGUAGE_POLICY))
    return plan


def _verify_clone_lineage(value, source_plan, plan, output):
    """Verify frozen task identity without inventing new paid-call receipts."""
    source = Path(value["sourceCandidateDirectory"])
    target = Path(value["targetCandidateDirectory"])
    if (source == target or source.is_relative_to(target) or target.is_relative_to(source)
            or not Path(value["sourceAudioAuditDirectory"]).is_relative_to(source)
            or not output.resolve().is_relative_to(target)
            or source_plan["classroomId"] == plan["classroomId"]):
        raise ValueError("audio_clone_requires_distinct_candidates_and_classrooms")
    for directory, expected in ((source, source_plan), (target, plan)):
        if directory.is_symlink():
            raise ValueError("audio_clone_candidate_symlink")
        paths = [directory / name for name in ("input.json", "classroom.json")]
        if any(path.is_symlink() or not path.is_file() for path in paths):
            raise ValueError("audio_clone_frozen_candidate_required")
        frozen, room = [json.loads(path.read_text()) for path in paths]
        if (frozen.get("taskId") != value["taskId"] or frozen.get("binding") != expected["binding"]
                or frozen.get("inputSha256") != digest({k: v for k, v in frozen.items() if k != "inputSha256"})
                or room.get("id") != expected["classroomId"] or digest(room) != expected["sourceSha256"]
                or build_audio_plan(room, frozen["binding"], expected["runtimeOrigin"],
                    audio_language_policy=audio_language_policy_from_plan(expected)) != expected):
            raise ValueError("audio_clone_frozen_lineage_mismatch")


def same_inherited_teaching_cue(old, new, *, allow_inserted_scenes=False):
    """Only v4 may shift a scene's index; all other cue fields stay exact."""
    if not allow_inserted_scenes:
        return old == new
    return ({k: v for k, v in old.items() if k != 'sceneOrder'}
            == {k: v for k, v in new.items() if k != 'sceneOrder'})


def _inheritance_targets(value, plan, output, media, teacher):
    if value is None:
        return {}
    validate_audio_inheritance(value)
    source = Path(value["sourceAudioAuditDirectory"])
    if source == output.resolve() or value["sourcePlanSha256"] == digest(plan) or value["sourceSha256"] == plan["sourceSha256"]:
        raise ValueError("audio_inheritance_requires_distinct_source")
    if value["targetPlanSha256"] != digest(plan) or value["targetSourceSha256"] != plan["sourceSha256"]:
        raise ValueError("audio_inheritance_target_mismatch")
    source_plan = json.loads((source / "plan.json").read_text())
    source_audit = json.loads((source / "audit.json").read_text())
    if (digest(source_plan) != value["sourcePlanSha256"] or digest(source_audit) != value["sourceAuditSha256"]
            or source_plan.get("sourceSha256") != value["sourceSha256"]
            or source_plan.get("schemaVersion") not in {"mira.textbook.batch-audio.v1", "mira.textbook.batch-audio.v2"}
            or source_audit.get("schemaVersion") != "mira.textbook.batch-audio-audit.v1"
            or source_audit.get("planSha256") != digest(source_plan)
            or source_plan.get("publicationAllowed") is not False or source_audit.get("publicationAllowed") is not False):
        raise ValueError("audio_inheritance_source_evidence_mismatch")
    if _plan_uses_english_auto(source_plan) != _plan_uses_english_auto(plan):
        raise ValueError("audio_inheritance_language_policy_mismatch")
    inserted_scenes = value["schemaVersion"] == AUDIO_SCENE_INSERTION_CLONE_SCHEMA
    inserted_cues = value["schemaVersion"] in {AUDIO_INSERTION_CLONE_SCHEMA, AUDIO_SCENE_INSERTION_CLONE_SCHEMA}
    clone = value["schemaVersion"] in {AUDIO_CLONE_INHERITANCE_SCHEMA, AUDIO_INSERTION_CLONE_SCHEMA, AUDIO_SCENE_INSERTION_CLONE_SCHEMA}
    identity_keys = ("binding", "teacher", "runtimeOrigin") if clone else ("binding", "teacher", "classroomId", "runtimeOrigin")
    for key in identity_keys:
        if source_plan.get(key) != plan[key]:
            raise ValueError("audio_inheritance_identity_mismatch")
    if clone:
        _verify_clone_lineage(value, source_plan, plan, output)
    source_media = media
    if clone:
        source_id = source_plan["classroomId"]
        if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", source_id):
            raise ValueError("audio_clone_source_identity_invalid")
        source_media = media.parent.parent / source_id / "audio"
        if (source_media.parent.is_symlink() or source_media.is_symlink()
                or not source_media.resolve().is_relative_to(media.parent.parent.resolve())):
            raise ValueError("audio_clone_source_media_path_invalid")
    old_workload = {(item["sceneId"], item["id"]): item for item in source_plan["workload"]}
    new_workload = {(item["sceneId"], item["id"]): item for item in plan["workload"]}
    old_segments = {(item["sceneId"], item["segmentId"]): item for item in source_audit["segments"]}
    if (len(old_workload) != len(source_plan["workload"])
            or len(new_workload) != len(plan["workload"])
            or len(old_segments) != len(source_audit["segments"])):
        raise ValueError("audio_inheritance_duplicate_source_identity")
    old_order = {key: index for index, key in enumerate(old_workload)}
    new_order = {key: index for index, key in enumerate(new_workload)}
    # v3 permits new cues between existing cues, never moving an existing cue.
    # The exact per-cue payload below still includes scene order, text and kind;
    # global workload offsets are not part of the original provider identity.
    if inserted_cues and ([key for key in old_workload if key in new_workload]
                          != [key for key in new_workload if key in old_workload]):
        raise ValueError("audio_inheritance_teaching_segment_changed")
    if inserted_scenes:
        old_scenes = list(dict.fromkeys(item['sceneId'] for item in source_plan['workload']))
        new_scenes = list(dict.fromkeys(item['sceneId'] for item in plan['workload']))
        if old_scenes != [scene for scene in new_scenes if scene in old_scenes]:
            raise ValueError('audio_inheritance_source_scene_removed_or_reordered')
    targets = {}
    for entry in value["segments"]:
        key = entry["sceneId"], entry["segmentId"]
        if (key not in old_workload or key not in new_workload
                or not same_inherited_teaching_cue(old_workload[key], new_workload[key],
                                                   allow_inserted_scenes=inserted_scenes)
                or not inserted_cues and old_order[key] != new_order[key]):
            raise ValueError("audio_inheritance_teaching_segment_changed")
        item = new_workload[key]
        source_segment = old_segments.get(key, {})
        page_proof = source_segment.get("pageNumberEquivalence")
        page_receipt = None
        if page_proof is not None:
            if (source_plan["binding"]["subject"] != "chinese"
                    or output.name != "audio-audit-page-numbers-v1"):
                raise ValueError("audio_inheritance_page_number_policy_required")
            page_receipt = validate_page_number_equivalence(item["text"], page_proof)
        if (source_segment.get("similarityBps") != entry["similarityBps"]
                or (page_receipt is None and
                    source_segment.get("literalScoreBps", source_segment.get("similarityBps", 0)) < 8500)
                or source_segment.get("inheritedFrom") is not None
                or any(source_segment.get(field) != entry[field] for field in
                       ("ttsRequestId", "asrRequestId", "audioSha256", "textSha256"))):
            raise ValueError("audio_inheritance_requires_original_passed_segment")
        # A paid source request includes its ORIGINAL scene_order. Never
        # reconstruct that receipt with a shifted target scene index.
        tts_id, old_identity, text_hash, tts_payload = _segment_requests(source_plan, old_workload[key], teacher)
        if tts_id != entry["ttsRequestId"] or text_hash != entry["textSha256"]:
            raise ValueError("audio_inheritance_request_identity_mismatch")
        tts = _known_success(source, tts_id, tts_payload)
        asr_id = entry["asrRequestId"]
        asr = _known_success(source, asr_id, {**old_identity, "request_id": asr_id,
            "tts_request_id": tts_id, "audio_sha256": entry["audioSha256"]})
        if clone and _plan_uses_english_auto(source_plan):
            # A v2 plan or request prefix alone is not evidence that the
            # original paid calls used Auto. Reuse the native client's exact
            # policy validation without constructing a client or making a GET.
            for operation, request_id, receipt in (("tts", tts_id, tts), ("asr", asr_id, asr)):
                OpenMaicFullRuntimeClient._validate_textbook_audio_namespace({
                    "subject": source_plan["binding"]["subject"], "requestId": request_id,
                    **({"ttsRequestId": tts_id} if operation == "asr" else {}),
                }, operation)
                OpenMaicFullRuntimeClient._textbook_audio_response_policy(
                    {**receipt, "state": receipt["status"]}, request_id)
        if (digest(tts) != entry["ttsReceiptSha256"] or digest(asr) != entry["asrReceiptSha256"]
                or tts.get("audioSha256") != entry["audioSha256"]):
            raise ValueError("audio_inheritance_receipt_mismatch")
        transcript = asr.get("transcript")
        literal_score = asr_similarity_bps(item["text"], transcript) if isinstance(transcript, str) else None
        if page_receipt is not None and (page_receipt != asr
                or source_segment.get("literalScoreBps") != literal_score
                or entry["similarityBps"] != 10000):
            raise ValueError("audio_inheritance_page_number_receipt_mismatch")
        if (not isinstance(transcript, str) or not transcript.strip()
                or asr.get("transcriptSha256") != hashlib.sha256(transcript.encode()).hexdigest()
                or (10000 if page_receipt is not None else literal_score) != entry["similarityBps"]):
            raise ValueError("audio_inheritance_transcript_mismatch")
        audio_path = source_media / f"{tts_id}.wav"
        if audio_path.is_symlink() or not audio_path.is_file() or hashlib.sha256(audio_path.read_bytes()).hexdigest() != entry["audioSha256"]:
            raise ValueError("audio_inheritance_audio_mismatch")
        target_tts_id, _, _, _ = _segment_requests(plan, item, teacher)
        target_asr_id = _asr_request_id(plan, target_tts_id, entry["audioSha256"])
        if (output / f"{target_tts_id}.json").exists() or (output / f"{target_asr_id}.json").exists():
            raise ValueError("audio_inheritance_conflicts_with_target_dispatch")
        evidence = {"schemaVersion": value["schemaVersion"],
                "sourceAudioAuditDirectory": str(source), "sourcePlanSha256": digest(source_plan),
                "sourceAuditSha256": digest(source_audit), "sourceSha256": source_plan["sourceSha256"],
                "targetPlanSha256": digest(plan), "targetSourceSha256": plan["sourceSha256"],
                "segment": deepcopy(entry)}
        if clone:
            evidence.update({key: value[key] for key in
                ("taskId", "sourceCandidateDirectory", "targetCandidateDirectory")})
        checkpoint = output / f"{tts_id}.inheritance.json"
        if checkpoint.exists() and json.loads(checkpoint.read_text()) != evidence:
            raise RuntimeError("frozen_audio_inheritance_segment_changed")
        targets[key] = {"ttsId": tts_id, "tts": tts, "asrId": asr_id, "asr": asr,
                        "sourceAudioPath": audio_path, "evidence": evidence,
                        "pageNumberEquivalence": page_proof}
    return targets


def _inheritance_set_targets(value, plan, output, media, teacher):
    frozen = normalize_audio_inheritance(value)
    targets = {}
    for manifest in (frozen or {}).get("manifests", []):
        targets.update(_inheritance_targets(manifest, plan, output, media, teacher))
    return frozen, targets


def narrate_candidate(runtime, classroom, binding, output, classroom_directory, *, progress=lambda value: None,
                      asr_reconciliation=None, audio_inheritance=None, audio_language_policy=None,
                      allow_page_number_equivalence=False):
    """Return an audited private candidate; never install a student course."""
    required = {"editionId", "revisionId", "gradeCode", "subject", "schoolSystem", "volume"}
    if not required <= set(binding) or binding["subject"] not in {"chinese", "math", "english", "science"}:
        raise ValueError("exact_textbook_binding_required")
    if urlparse(runtime.base_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("local_runtime_required")
    classroom_id = classroom.get("id")
    if (not isinstance(classroom_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", classroom_id)
            or classroom.get("stage", {}).get("id") != classroom_id):
        raise ValueError("invalid_classroom_identity")
    teacher = get_formal_subject_qwen_voice_identity(binding["subject"])
    workload = narration_workload(classroom)
    output, root = Path(output).resolve(), Path(classroom_directory).resolve()
    if allow_page_number_equivalence and (binding['subject'] != 'chinese'
            or output.name != 'audio-audit-page-numbers-v1' or asr_reconciliation is not None):
        raise ValueError('page_number_review_requires_separate_chinese_audit')
    if audio_language_policy is not None:
        if output.name == "audio-audit":
            raise ValueError("english_auto_language_requires_distinct_audit_directory")
        if output.exists() and not (output / "plan.json").is_file() and any(output.iterdir()):
            raise ValueError("english_auto_language_requires_empty_or_matching_audit_directory")
    output.mkdir(parents=True, exist_ok=True)
    original_file = root / f"{classroom_id}.json"
    if not original_file.is_file():
        raise RuntimeError("original_runtime_classroom_missing")
    # Files are private generated content, not a license to replace editor work.
    from services.textbook_preview_audio import core_content
    canonical_source = core_content(classroom)
    def core(value):
        value = core_content(value)
        for scene in value.get("scenes", []):
            if scene.get("type") == "interactive" and isinstance(scene.get("content", {}).get("html"), str):
                scene["content"]["html"] = without_audio_helper(scene["content"]["html"])
            for q in scene.get("content", {}).get("questions", []):
                q.pop("questionAudioUrl", None)
                q.pop("feedbackAudioUrl", None)
        return value
    if core(json.loads(original_file.read_text())) != core(canonical_source):
        raise RuntimeError("runtime_classroom_changed")
    plan = build_audio_plan(classroom, binding, runtime.base_url, audio_language_policy=audio_language_policy)
    with (output / "operator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan_path = output / "plan.json"
        if plan_path.exists() and json.loads(plan_path.read_text()) != plan:
            raise RuntimeError("frozen_audio_plan_changed")
        if not plan_path.exists():
            save_json(plan_path, plan)
        spelling_path = output / 'page-number-policy.json'
        spelling_policy = {'schemaVersion': 'mira.textbook.page-number-policy.v1',
                           'planSha256': digest(plan), 'allowed': True}
        if spelling_path.exists() and (not allow_page_number_equivalence
                or json.loads(spelling_path.read_text()) != spelling_policy):
            raise ValueError('page_number_review_policy_changed')
        if allow_page_number_equivalence and not spelling_path.exists():
            save_json(spelling_path, spelling_policy)
        narrated, segments, interactive_urls = deepcopy(classroom), [], {}
        media = root / classroom_id / "audio"
        media.mkdir(parents=True, exist_ok=True)
        inheritance_path = output / "inheritance-manifest.json"
        inheritance_set = normalize_audio_inheritance(audio_inheritance)
        if inheritance_path.exists() and (inheritance_set is None
                or normalize_audio_inheritance(json.loads(inheritance_path.read_text())) != inheritance_set):
            raise RuntimeError("frozen_audio_inheritance_manifest_required")
        inheritance_set, inheritance_targets = _inheritance_set_targets(
            inheritance_set, plan, output, media, teacher)
        if not allow_page_number_equivalence and any(
                target.get("pageNumberEquivalence") is not None for target in inheritance_targets.values()):
            raise ValueError("audio_inheritance_page_number_policy_required")
        reconciliation_targets = _reconciliation_targets(asr_reconciliation, plan, output, media, teacher)
        if inheritance_targets.keys() & reconciliation_targets.keys():
            raise ValueError("audio_inheritance_reconciliation_overlap")
        if inheritance_set is not None and not inheritance_path.exists():
            save_json(inheritance_path, inheritance_set)
        for i, item in enumerate(workload, 1):
            tts_id, identity, text_hash, tts_payload = _segment_requests(plan, item, teacher)
            inherited = inheritance_targets.get((item["sceneId"], item["id"]))
            if inherited:
                tts_id, tts = inherited["ttsId"], inherited["tts"]
                checkpoint = output / f"{tts_id}.inheritance.json"
                if checkpoint.exists() and json.loads(checkpoint.read_text()) != inherited["evidence"]:
                    raise RuntimeError("frozen_audio_inheritance_segment_changed")
                if not checkpoint.exists():
                    save_json(checkpoint, inherited["evidence"])
            else:
                tts = _external_once(runtime, output / f"{tts_id}.json", tts_id, "tts", tts_payload)
            audio_path = media / f"{tts_id}.wav"
            audio = (audio_path.read_bytes() if audio_path.exists() else
                     inherited["sourceAudioPath"].read_bytes() if inherited else
                     runtime.download_formal_audio_tts(tts_id, expected_sha256=tts["audioSha256"]))
            if hashlib.sha256(audio).hexdigest() != tts["audioSha256"]:
                raise RuntimeError("narration_audio_hash_changed")
            with wave.open(io.BytesIO(audio)) as wav:
                duration = wav.getnframes() / wav.getframerate()
                if not 0 < duration <= 240 or wav.getnchannels() != 1 or wav.getsampwidth() != 2:
                    raise ValueError("invalid_narration_wav")
            if not audio_path.exists():
                with audio_path.open("xb") as stream:
                    stream.write(audio)
            if inherited:
                asr_id, asr = inherited["asrId"], inherited["asr"]
            else:
                asr_id = _asr_request_id(plan, tts_id, tts["audioSha256"])
                asr = _external_once(runtime, output / f"{asr_id}.json", asr_id, "asr",
                                     {**identity, "request_id": asr_id, "tts_request_id": tts_id,
                                      "audio_sha256": tts["audioSha256"]})
            if not isinstance(asr.get("transcript"), str) or not asr["transcript"].strip():
                raise RuntimeError("asr_transcript_recovery_required_no_retry")
            similarity = asr_similarity_bps(item["text"], asr["transcript"])
            literal_score = similarity
            spelling_proof = (page_number_equivalence(item['text'], asr)
                              if allow_page_number_equivalence and literal_score < 10000 else None)
            if spelling_proof is not None:
                similarity = 10000
            reconciliation = None
            target = reconciliation_targets.get((item["sceneId"], item["id"]))
            if target:
                entry = target["authorization"]["segment"]
                if (literal_score >= 8500 or literal_score != entry["originalSimilarityBps"]
                        or digest(asr) != entry["originalAsrReceiptSha256"]):
                    raise RuntimeError("asr_reconciliation_original_receipt_changed")
                authorization_path = output / f"{target['requestId']}.authorization.json"
                if authorization_path.exists():
                    if json.loads(authorization_path.read_text()) != target["authorization"]:
                        raise RuntimeError("frozen_asr_reconciliation_changed")
                else:
                    save_json(authorization_path, target["authorization"])
                reconciled = _external_once(runtime, output / f"{target['requestId']}.json",
                    target["requestId"], "asr", {**identity, "request_id": target["requestId"],
                    "tts_request_id": tts_id, "audio_sha256": tts["audioSha256"]})
                if not isinstance(reconciled.get("transcript"), str) or not reconciled["transcript"].strip():
                    raise RuntimeError("asr_transcript_recovery_required_no_retry")
                similarity = asr_similarity_bps(item["text"], reconciled["transcript"])
                reconciliation = {**target["authorization"]["segment"],
                    "reconciliationAsrRequestId": target["requestId"], "reconciliationSimilarityBps": similarity,
                    "authorizationSha256": digest(target["authorization"])}
            url = f"/api/classroom-media/{classroom_id}/audio/{tts_id}.wav"
            scene = next(s for s in narrated["scenes"] if s["id"] == item["sceneId"])
            if item["kind"] == "speech":
                action = next(a for a in scene["actions"] if a["id"] == item["id"])
                action.update(audioId=tts_id, audioUrl=url,
                              audioMetadata={"schemaVersion": "mira.openmaic.speech-audio.v1",
                                             "providerId": teacher.tts_provider_id, "modelId": teacher.tts_model_id,
                                             "voiceId": teacher.voice_id, "fallbackUsed": False})
            elif item["kind"] == "interactive":
                interactive_urls.setdefault(item["sceneId"], {})[item["cueId"]] = url
            else:
                question = next(q for q in scene["content"]["questions"] if q["id"] == item["questionId"])
                question["questionAudioUrl" if item["kind"] == "prompt" else "feedbackAudioUrl"] = url
            segment = {"sceneId": item["sceneId"], "segmentId": item["id"], "textSha256": text_hash,
                             "ttsRequestId": tts_id, "audioSha256": tts["audioSha256"],
                             "durationSeconds": round(duration, 3), "asrRequestId": (
                                 target["requestId"] if target else asr_id),
                             "literalScoreBps": literal_score, "similarityBps": similarity, "audioUrl": url}
            if reconciliation:
                segment["asrReconciliation"] = reconciliation
            if spelling_proof is not None:
                segment['pageNumberEquivalence'] = spelling_proof
            if inherited:
                segment["inheritedFrom"] = inherited["evidence"]
            segments.append(segment)
            save_json(output / "narrated-classroom.json", narrated)
            result = {"schemaVersion": "mira.textbook.batch-audio-audit.v1", "planSha256": digest(plan),
                      "expectedSegments": len(workload), "completedSegments": len(segments),
                      "segments": segments, "allSegmentsPassed": False,
                      "semanticPronunciationReview": "pending", "interactiveStateNarrationReview": "pending",
                      "interactiveCuesCompleted": sum(len(urls) for urls in interactive_urls.values()),
                      "publicationAllowed": False}
            save_json(output / "audit.json", result)
            progress({"completed": i, "total": len(workload), "similarityBps": similarity})
            if similarity < 8500:
                raise RuntimeError("narration_asr_semantic_review_required_no_retry")
        for scene in narrated["scenes"]:
            if scene["id"] in interactive_urls:
                scene["content"]["html"] = bind_interactive_audio(
                    scene["content"]["html"], interactive_urls[scene["id"]], classroom_id)
        save_json(output / "narrated-classroom.json", narrated)
        # Preserve the original input snapshot. Save only after all audio passes.
        if core(runtime.get_classroom(classroom_id)) != core(canonical_source):
            raise RuntimeError("runtime_classroom_changed_before_audio_save")
        runtime.save_preview_classroom(narrated)
        readback = runtime.get_classroom(classroom_id)
        # Timestamp normalization is permitted; losing even one audio binding is not.
        if core(readback) != core(narrated) or _audio_bindings(readback) != _audio_bindings(narrated):
            raise RuntimeError("narrated_classroom_save_mismatch")
        result["allSegmentsPassed"] = True
        result["sha256"] = digest(result)
        save_json(output / "audit.json", result)
        return result
